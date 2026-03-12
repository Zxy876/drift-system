package com.driftmc.exit;

import java.io.IOException;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.driftmc.hud.QuestLogHud;
import com.driftmc.hud.RecommendationHud;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonSyntaxException;
import com.google.gson.reflect.TypeToken;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

/**
 * Detects exit phrases in chat and bridges to the backend exit workflow.
 */
public final class ExitIntentDetector {

    private static final List<String> DEFAULT_ALIASES = List.of(
            "结束剧情",
            "离开关卡",
            "退出剧情",
            "退出",
            "leave",
            "exit");

    private static final long PROFILE_TTL_MILLIS = 60_000L;

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final WorldPatchExecutor worldPatcher;
    private final RecommendationHud recommendationHud;
    private final QuestLogHud questLogHud;
    private final Gson gson = new Gson();
    private final Type mapType = new TypeToken<Map<String, Object>>() {
    }.getType();

    private final Map<String, ExitProfile> profileCache = new ConcurrentHashMap<>();
    private final Set<String> profileRequests = ConcurrentHashMap.newKeySet();
    private final Set<String> exitRequests = ConcurrentHashMap.newKeySet();

    public ExitIntentDetector(JavaPlugin plugin, BackendClient backend, WorldPatchExecutor worldPatcher,
            RecommendationHud recommendationHud, QuestLogHud questLogHud) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.backend = Objects.requireNonNull(backend, "backend");
        this.worldPatcher = Objects.requireNonNull(worldPatcher, "worldPatcher");
        this.recommendationHud = recommendationHud;
        this.questLogHud = questLogHud;
    }

    /**
     * Attempts to handle an exit phrase. Returns true if the chat message is consumed.
     */
    public boolean handle(Player player, String message) {
        if (player == null || message == null || message.isBlank()) {
            return false;
        }

        String playerName = player.getName();
        ensureProfile(playerName);

        if (!matchesExitIntent(playerName, message)) {
            return false;
        }

        triggerExit(player);
        return true;
    }

    private void ensureProfile(String playerName) {
        ExitProfile profile = profileCache.get(playerName);
        long now = System.currentTimeMillis();
        if (profile == null || now - profile.updatedAt > PROFILE_TTL_MILLIS) {
            fetchExitProfile(playerName);
        }
    }

    private void fetchExitProfile(String playerName) {
        if (!profileRequests.add(playerName)) {
            return;
        }

        backend.getAsync("/world/state/" + playerName, new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                profileRequests.remove(playerName);
                plugin.getLogger().log(Level.FINE,
                        "[ExitDetector] failed to fetch exit profile for {0}: {1}",
                        new Object[]{playerName, e.getMessage()});
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                try (Response res = response) {
                    String payload = res.body() != null ? res.body().string() : "{}";
                    if (!res.isSuccessful()) {
                        plugin.getLogger().log(Level.FINE,
                                "[ExitDetector] exit profile HTTP {0} for {1}",
                                new Object[]{res.code(), playerName});
                        return;
                    }
                    parseExitProfile(playerName, payload);
                } catch (JsonSyntaxException ex) {
                    plugin.getLogger().log(Level.WARNING,
                            "[ExitDetector] invalid exit profile payload for " + playerName,
                            ex);
                } finally {
                    profileRequests.remove(playerName);
                }
            }
        });
    }

    private void parseExitProfile(String playerName, String json) {
        JsonObject root;
        try {
            JsonElement parsed = JsonParser.parseString(json);
            if (!parsed.isJsonObject()) {
                profileCache.remove(playerName);
                return;
            }
            root = parsed.getAsJsonObject();
        } catch (JsonSyntaxException ex) {
            profileCache.remove(playerName);
            throw ex;
        }

        JsonObject profileObj = null;
        if (root.has("exit_profile") && root.get("exit_profile").isJsonObject()) {
            profileObj = root.getAsJsonObject("exit_profile");
        } else if (root.has("world_state") && root.get("world_state").isJsonObject()) {
            JsonObject stateObj = root.getAsJsonObject("world_state");
            if (stateObj.has("exit_profile") && stateObj.get("exit_profile").isJsonObject()) {
                profileObj = stateObj.getAsJsonObject("exit_profile");
            }
        }

        Set<String> aliases = new LinkedHashSet<>();
        if (profileObj != null) {
            JsonElement aliasesEl = profileObj.get("aliases");
            if (aliasesEl != null) {
                if (aliasesEl.isJsonArray()) {
                    JsonArray array = aliasesEl.getAsJsonArray();
                    for (JsonElement element : array) {
                        if (element != null && element.isJsonPrimitive()) {
                            String alias = element.getAsString();
                            if (alias != null && !alias.isBlank()) {
                                aliases.add(alias);
                            }
                        }
                    }
                } else if (aliasesEl.isJsonPrimitive()) {
                    String alias = aliasesEl.getAsString();
                    if (alias != null && !alias.isBlank()) {
                        aliases.add(alias);
                    }
                }
            }
        }

        profileCache.put(playerName, new ExitProfile(aliases, System.currentTimeMillis()));
    }

    private boolean matchesExitIntent(String playerName, String message) {
        String normalized = normalize(message);
        if (normalized.isEmpty()) {
            return false;
        }

        Set<String> aliases = new LinkedHashSet<>(DEFAULT_ALIASES);
        ExitProfile profile = profileCache.get(playerName);
        if (profile != null && !profile.aliases.isEmpty()) {
            aliases.addAll(profile.aliases);
        }

        for (String alias : aliases) {
            String target = normalize(alias);
            if (!target.isEmpty() && normalized.contains(target)) {
                return true;
            }
        }
        return false;
    }

    private void triggerExit(Player player) {
        final UUID playerId = player.getUniqueId();
        final String playerName = player.getName();

        if (!exitRequests.add(playerName)) {
            player.sendMessage(ChatColor.GOLD + "剧情正在收尾，请稍候…");
            return;
        }

        player.sendMessage(ChatColor.GOLD + "⌛ 正在结束剧情，请稍候…");

        Map<String, Object> body = new HashMap<>();
        body.put("player_id", playerName);
        String jsonBody = gson.toJson(body);

        backend.postJsonAsync("/world/story/end", jsonBody, new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                exitRequests.remove(playerName);
                Bukkit.getScheduler().runTask(plugin, () -> {
                    Player target = Bukkit.getPlayer(playerId);
                    if (target != null && target.isOnline()) {
                        target.sendMessage(ChatColor.RED + "结束剧情失败：" + e.getMessage());
                    }
                });
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                boolean success;
                int statusCode;
                String payload;
                try (Response res = response) {
                    success = res.isSuccessful();
                    statusCode = res.code();
                    okhttp3.ResponseBody body = res.body();
                    payload = body != null ? body.string() : "{}";
                }
                handleExitResponse(playerId, playerName, success, statusCode, payload);
            }
        });
    }

    private void handleExitResponse(UUID playerId, String playerName, boolean success, int statusCode, String payload) {
        Bukkit.getScheduler().runTask(plugin, () -> {
            exitRequests.remove(playerName);

            Player target = Bukkit.getPlayer(playerId);
            if (target == null || !target.isOnline()) {
                return;
            }

            if (!success) {
                target.sendMessage(ChatColor.RED + "结束剧情失败：后端返回状态 " + statusCode);
                return;
            }

            JsonObject root;
            try {
                JsonElement parsed = JsonParser.parseString(payload);
                if (!parsed.isJsonObject()) {
                    target.sendMessage(ChatColor.RED + "结束剧情失败：响应格式无效。");
                    return;
                }
                root = parsed.getAsJsonObject();
            } catch (JsonSyntaxException ex) {
                plugin.getLogger().log(Level.WARNING, "[ExitDetector] malformed exit response", ex);
                target.sendMessage(ChatColor.RED + "结束剧情失败：无法解析服务器响应。");
                return;
            }

            JsonObject worldPatchObj = null;
            if (root.has("world_patch") && root.get("world_patch").isJsonObject()) {
                worldPatchObj = root.getAsJsonObject("world_patch");
            }

            if (worldPatchObj != null && worldPatchObj.size() > 0) {
                Map<String, Object> patch = gson.fromJson(worldPatchObj, mapType);
                worldPatcher.execute(target, patch);
                deliverExitSummary(target, worldPatchObj);
            } else {
                target.sendMessage(ChatColor.YELLOW + "剧情已结束，但没有返回场景清理数据。");
            }

            if (questLogHud != null) {
                questLogHud.handleLevelExit(target);
            }

            if (recommendationHud != null) {
                recommendationHud.showRecommendations(target, RecommendationHud.Trigger.AUTO_EXIT);
            }

            profileCache.remove(playerName);
        });
    }

    private void deliverExitSummary(Player player, JsonObject patchObj) {
        if (patchObj == null || patchObj.size() == 0) {
            return;
        }

        JsonObject summary = null;
        if (patchObj.has("exit_summary") && patchObj.get("exit_summary").isJsonObject()) {
            summary = patchObj.getAsJsonObject("exit_summary");
        }
        if (summary == null || summary.size() == 0) {
            return;
        }

        String farewell = getAsString(summary, "farewell");
        if (farewell != null && !farewell.isBlank()) {
            player.sendMessage(ChatColor.GOLD + "★ 剧情摘要：" + ChatColor.WHITE + farewell);
        }

        JsonObject hub = null;
        if (summary.has("hub") && summary.get("hub").isJsonObject()) {
            hub = summary.getAsJsonObject("hub");
        }
        if (hub != null && hub.size() > 0) {
            String worldName = getAsString(hub, "world");
            double x = getAsDouble(hub, "x");
            double y = getAsDouble(hub, "y");
            double z = getAsDouble(hub, "z");
            player.sendMessage(ChatColor.GRAY + "返回位置 → " + ChatColor.AQUA
                    + (worldName == null || worldName.isBlank() ? "KunmingLakeHub" : worldName)
                    + ChatColor.WHITE + String.format(Locale.ROOT, " (%.1f, %.1f, %.1f)", x, y, z));
        }

        JsonElement aliasEl = summary.get("aliases");
        if (aliasEl != null && aliasEl.isJsonArray()) {
            JsonArray array = aliasEl.getAsJsonArray();
            List<String> aliasList = new ArrayList<>();
            for (JsonElement element : array) {
                if (element != null && element.isJsonPrimitive()) {
                    String alias = element.getAsString();
                    if (alias != null && !alias.isBlank()) {
                        aliasList.add(alias);
                    }
                }
            }
            if (!aliasList.isEmpty()) {
                int limit = Math.min(aliasList.size(), 4);
                String preview = String.join(" / ", aliasList.subList(0, limit));
                player.sendMessage(ChatColor.DARK_AQUA + "下次可以说：" + ChatColor.WHITE + preview);
            }
        }
    }

    private String getAsString(JsonObject obj, String key) {
        if (obj == null || key == null) {
            return null;
        }
        JsonElement element = obj.get(key);
        if (element == null || element.isJsonNull()) {
            return null;
        }
        if (element.isJsonPrimitive()) {
            return element.getAsString();
        }
        return null;
    }

    private double getAsDouble(JsonObject obj, String key) {
        if (obj == null || key == null) {
            return 0.0D;
        }
        JsonElement element = obj.get(key);
        if (element == null || element.isJsonNull()) {
            return 0.0D;
        }
        try {
            return element.getAsDouble();
        } catch (NumberFormatException | UnsupportedOperationException ex) {
            return 0.0D;
        }
    }

    private String normalize(String input) {
        if (input == null) {
            return "";
        }
        String lower = input.toLowerCase(Locale.ROOT);
        StringBuilder sb = new StringBuilder(lower.length());
        for (int i = 0; i < lower.length(); i++) {
            char c = lower.charAt(i);
            int type = Character.getType(c);
            boolean skip = switch (type) {
                case Character.SPACE_SEPARATOR,
                        Character.LINE_SEPARATOR,
                        Character.PARAGRAPH_SEPARATOR,
                        Character.CONTROL,
                        Character.FORMAT,
                        Character.DASH_PUNCTUATION,
                        Character.END_PUNCTUATION,
                        Character.CONNECTOR_PUNCTUATION,
                        Character.START_PUNCTUATION,
                        Character.OTHER_PUNCTUATION,
                        Character.INITIAL_QUOTE_PUNCTUATION,
                        Character.FINAL_QUOTE_PUNCTUATION -> true;
                default -> false;
            };
            if (skip) {
                continue;
            }
            sb.append(c);
        }
        return sb.toString().trim();
    }

    private static final class ExitProfile {
        final Set<String> aliases;
        final long updatedAt;

        ExitProfile(Set<String> aliases, long updatedAt) {
            this.aliases = aliases != null ? new LinkedHashSet<>(aliases) : new LinkedHashSet<>();
            this.updatedAt = updatedAt;
        }
    }
}

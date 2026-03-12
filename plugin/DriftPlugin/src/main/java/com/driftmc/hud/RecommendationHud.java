package com.driftmc.hud;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.driftmc.story.LevelIds;
import com.driftmc.story.StoryManager;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParseException;
import com.google.gson.JsonParser;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.event.HoverEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

/**
 * RecommendationHud — fetches StoryGraph recommendations and surfaces
 * them via ActionBar + clickable chat components.
 */
public final class RecommendationHud {

    public enum Trigger {
        COMMAND,
        AUTO_EXIT
    }

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final StoryManager storyManager;

    public RecommendationHud(JavaPlugin plugin, BackendClient backend, StoryManager storyManager) {
        this.plugin = plugin;
        this.backend = backend;
        this.storyManager = storyManager;
    }

    public void showRecommendations(Player player, Trigger trigger) {
        if (player == null) {
            return;
        }

        final UUID playerId = player.getUniqueId();
        final String playerName = player.getName();
        final String currentLevel = storyManager != null ? storyManager.getCurrentLevel(player) : null;

        StringBuilder path = new StringBuilder();
        path.append("/world/story/")
            .append(urlSegment(playerName))
            .append("/recommendations?limit=3");
        if (currentLevel != null && !currentLevel.isBlank()) {
            path.append("&current_level=")
                .append(encode(currentLevel));
        }

        backend.getAsync(path.toString(), new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                plugin.getLogger().log(Level.FINE,
                        "[RecommendationHud] backend fetch failed for {0}: {1}",
                        new Object[] { playerName, e.getMessage() });
                if (trigger == Trigger.COMMAND) {
                    Bukkit.getScheduler().runTask(plugin, () -> {
                        Player target = Bukkit.getPlayer(playerId);
                        if (target != null && target.isOnline()) {
                            target.sendMessage(Component.text("推荐系统暂时不可用，请稍后再试。", NamedTextColor.RED));
                        }
                    });
                }
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                int statusCode = response.code();
                boolean success = response.isSuccessful();
                List<Recommendation> recommendations = Collections.emptyList();
                String payload;
                try (Response res = response) {
                    okhttp3.ResponseBody body = res.body();
                    payload = body != null ? body.string() : "{}";
                }

                if (success) {
                    recommendations = parseRecommendations(payload);
                } else {
                    plugin.getLogger().log(Level.FINE,
                            "[RecommendationHud] HTTP {0} for {1}",
                            new Object[] { statusCode, playerName });
                }

                final List<Recommendation> finalRecommendations = recommendations;
                final boolean responseSuccess = success;

                Bukkit.getScheduler().runTask(plugin, () -> {
                    Player target = Bukkit.getPlayer(playerId);
                    if (target == null || !target.isOnline()) {
                        return;
                    }

                    if (!responseSuccess) {
                        if (trigger == Trigger.COMMAND) {
                            target.sendMessage(Component.text("推荐系统暂时不可用，请稍后再试。", NamedTextColor.RED));
                        }
                        return;
                    }

                    render(target, finalRecommendations, trigger);
                });
            }
        });
    }

    private void render(Player player, List<Recommendation> recs, Trigger trigger) {
        if (recs == null || recs.isEmpty()) {
            if (trigger == Trigger.COMMAND) {
                player.sendMessage(Component.text("暂时没有 StoryGraph 推荐章节，继续探索吧！", NamedTextColor.GRAY));
            }
            return;
        }

        Recommendation top = recs.get(0);
        String displayTitle = top.title != null && !top.title.isBlank() ? top.title : top.levelId;
        player.sendActionBar(Component.text("推荐章节：《" + displayTitle + "》", NamedTextColor.LIGHT_PURPLE));

        Component header = Component.text("✨ 推荐下一章：", NamedTextColor.LIGHT_PURPLE)
                .append(Component.text("《" + displayTitle + "》", NamedTextColor.GOLD));
        player.sendMessage(header);

        if (top.reasonSummary != null && !top.reasonSummary.isBlank()) {
            Component reasonLine = Component.text("理由：", NamedTextColor.GRAY)
                    .append(Component.text(top.reasonSummary, NamedTextColor.WHITE));
            player.sendMessage(reasonLine);
        }

        Component action = Component.text("点击前往 → ", NamedTextColor.AQUA)
                .append(Component.text("/level " + top.levelId, NamedTextColor.YELLOW))
                .clickEvent(ClickEvent.runCommand("/level " + top.levelId))
                .hoverEvent(HoverEvent.showText(Component.text("点击立刻前往推荐章节", NamedTextColor.GOLD)));
        player.sendMessage(action);

        if (recs.size() > 1) {
            player.sendMessage(Component.text("其他灵感：", NamedTextColor.GREEN));
            for (int i = 1; i < recs.size(); i++) {
                Recommendation rec = recs.get(i);
                String title = rec.title != null && !rec.title.isBlank() ? rec.title : rec.levelId;
                String highlight;
                if (rec.reasonSummary != null && !rec.reasonSummary.isBlank()) {
                    highlight = rec.reasonSummary;
                } else if (rec.reasons != null && !rec.reasons.isEmpty()) {
                    highlight = rec.reasons.get(0);
                } else {
                    highlight = String.format("得分 %.1f", rec.score);
                }
                Component line = Component.text("• ", NamedTextColor.GRAY)
                        .append(Component.text(title, NamedTextColor.WHITE))
                        .append(Component.text(" · ", NamedTextColor.DARK_GRAY))
                        .append(Component.text(highlight, NamedTextColor.AQUA));
                player.sendMessage(line);
            }
        }
    }

    private List<Recommendation> parseRecommendations(String json) {
        try {
            JsonElement parsed = JsonParser.parseString(json);
            if (!parsed.isJsonObject()) {
                return Collections.emptyList();
            }
            JsonObject root = parsed.getAsJsonObject();
            if (!root.has("recommendations") || !root.get("recommendations").isJsonArray()) {
                return Collections.emptyList();
            }

            JsonArray array = root.getAsJsonArray("recommendations");
            List<Recommendation> list = new ArrayList<>(array.size());
            for (JsonElement element : array) {
                if (element == null || !element.isJsonObject()) {
                    continue;
                }
                JsonObject obj = element.getAsJsonObject();
                String levelId = getAsString(obj, "level_id");
                if (levelId == null || levelId.isBlank()) {
                    continue;
                }
                Recommendation rec = new Recommendation();
                rec.levelId = LevelIds.canonicalizeLevelId(levelId);
                rec.title = getAsString(obj, "title");
                rec.score = getAsDouble(obj, "score");
                rec.reasonSummary = getAsString(obj, "reason_summary");
                rec.reasons = extractReasons(obj);
                list.add(rec);
            }
            return list;
        } catch (IllegalStateException | JsonParseException ex) {
            plugin.getLogger().log(Level.WARNING, "[RecommendationHud] failed to parse payload", ex);
            return Collections.emptyList();
        }
    }

    private List<String> extractReasons(JsonObject obj) {
        if (obj == null || !obj.has("reasons") || !obj.get("reasons").isJsonArray()) {
            return Collections.emptyList();
        }
        JsonArray array = obj.getAsJsonArray("reasons");
        List<String> reasons = new ArrayList<>(array.size());
        for (JsonElement element : array) {
            if (element != null && element.isJsonPrimitive()) {
                String value = element.getAsString();
                if (value != null && !value.isBlank()) {
                    reasons.add(value);
                }
            }
        }
        return reasons;
    }

    private String urlSegment(String text) {
        return encode(text != null ? text : "");
    }

    private String encode(String text) {
        return URLEncoder.encode(text, StandardCharsets.UTF_8);
    }

    private String getAsString(JsonObject obj, String key) {
        if (obj == null || key == null || !obj.has(key)) {
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
        if (obj == null || key == null || !obj.has(key)) {
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

    private static final class Recommendation {
        String levelId;
        String title;
        String reasonSummary;
        double score;
        List<String> reasons = Collections.emptyList();
    }
}

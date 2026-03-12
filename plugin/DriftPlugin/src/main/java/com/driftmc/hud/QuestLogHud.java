package com.driftmc.hud;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

/**
 * QuestLogHud renders the active quest/task snapshot returned by the backend.
 */
public final class QuestLogHud {

    public enum Trigger {
        COMMAND,
        RULE_EVENT,
        LEVEL_ENTER,
        LEVEL_EXIT
    }

    private final JavaPlugin plugin;
    private final BackendClient backend;
    private final Map<UUID, JsonObject> cache = new ConcurrentHashMap<>();

    public QuestLogHud(JavaPlugin plugin, BackendClient backend) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.backend = Objects.requireNonNull(backend, "backend");
    }

    /**
     * Fetches the latest quest log snapshot and renders it for the caller.
     */
    public void showQuestLog(Player player, Trigger trigger) {
        if (player == null) {
            return;
        }

        final UUID playerId = player.getUniqueId();
        final String playerName = player.getName();
        final String path = "/world/story/" + urlSegment(playerName) + "/quest-log";

        backend.getAsync(path, new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                plugin.getLogger().log(Level.FINE,
                        "[QuestLogHud] backend fetch failed for {0}: {1}",
                        new Object[] { playerName, e.getMessage() });
                if (trigger == Trigger.COMMAND) {
                    Bukkit.getScheduler().runTask(plugin, () -> {
                        Player target = Bukkit.getPlayer(playerId);
                        if (target != null && target.isOnline()) {
                            target.sendMessage(Component.text("任务日志暂时不可用，请稍后再试。", NamedTextColor.RED));
                        }
                    });
                }
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                boolean success;
                String payload;
                try (Response res = response) {
                    success = res.isSuccessful();
                    okhttp3.ResponseBody body = res.body();
                    payload = body != null ? body.string() : "{}";
                }

                JsonObject snapshot = null;
                if (success) {
                    snapshot = parseSnapshot(payload);
                }

                final JsonObject finalSnapshot = snapshot;
                final boolean responseSuccess = success;

                Bukkit.getScheduler().runTask(plugin, () -> {
                    Player target = Bukkit.getPlayer(playerId);
                    if (target == null || !target.isOnline()) {
                        return;
                    }

                    if (!responseSuccess) {
                        if (trigger == Trigger.COMMAND) {
                            target.sendMessage(Component.text("任务日志暂时不可用，请稍后再试。", NamedTextColor.RED));
                        }
                        return;
                    }

                    handleSnapshot(target, finalSnapshot, trigger);
                });
            }
        });
    }

    /**
     * Updates local cache and renders snapshot depending on trigger.
     */
    public void handleSnapshot(Player player, JsonObject snapshot, Trigger trigger) {
        if (player == null) {
            return;
        }

        if (snapshot == null || snapshot.size() == 0) {
            cache.remove(player.getUniqueId());
            if (trigger == Trigger.COMMAND) {
                player.sendMessage(Component.text("当前没有活跃任务。", NamedTextColor.GRAY));
            }
            if (trigger == Trigger.LEVEL_EXIT) {
                player.sendActionBar(Component.text("📘 当前章节已结束", NamedTextColor.GOLD));
            }
            return;
        }

        JsonObject previous = cache.get(player.getUniqueId());
        boolean changed = previous == null || !previous.equals(snapshot);
        cache.put(player.getUniqueId(), snapshot.deepCopy());

        if (trigger == Trigger.COMMAND || trigger == Trigger.LEVEL_ENTER) {
            renderSnapshot(player, snapshot, trigger);
        } else if (trigger == Trigger.RULE_EVENT && changed) {
            renderSnapshot(player, snapshot, trigger);
        }
    }

    /**
     * Reacts to quest nodes surfaced via RuleEventBridge (milestones/progress).
     */
    public void handleQuestNode(Player player, JsonObject node) {
        if (player == null || node == null || node.size() == 0) {
            return;
        }
        String type = getString(node, "type");
        if ("task_milestone".equalsIgnoreCase(type)) {
            String milestoneTitle = getString(node, "title");
            String taskTitle = getString(node, "task_title");
            int progress = getInt(node, "progress", -1);
            int count = getInt(node, "count", -1);
            showMilestoneAction(player, taskTitle, milestoneTitle, progress, count);
        } else if ("task_complete".equalsIgnoreCase(type)) {
            String taskTitle = getString(node, "title");
            player.sendActionBar(Component.text("✔ 任务完成：" + safeLabel(taskTitle), NamedTextColor.GREEN));
        }
    }

    /**
     * Clears cached quest data and surfaces a short exit cue.
     */
    public void handleLevelExit(Player player) {
        if (player == null) {
            return;
        }
        cache.remove(player.getUniqueId());
        player.sendActionBar(Component.text("📘 任务日志已归档", NamedTextColor.GOLD));
    }

    private void renderSnapshot(Player player, JsonObject snapshot, Trigger trigger) {
        JsonArray tasks = getArray(snapshot, "tasks");
        if (tasks == null || tasks.size() == 0) {
            if (trigger == Trigger.COMMAND || trigger == Trigger.LEVEL_ENTER) {
                player.sendMessage(Component.text("当前没有活跃任务。", NamedTextColor.GRAY));
            }
            return;
        }

        int remainingTotal = getInt(snapshot, "remaining_total", -1);
        String headerText = trigger == Trigger.RULE_EVENT ? "📘 任务更新" : "📘 任务日志";
        Component header = Component.text(headerText, NamedTextColor.AQUA);
        if (remainingTotal >= 0) {
            header = header.append(Component.text(" · 剩余 " + remainingTotal + " 项", NamedTextColor.GRAY));
        }
        player.sendMessage(header);

        String levelTitle = getString(snapshot, "level_title");
        if (levelTitle != null && !levelTitle.isBlank()) {
            player.sendMessage(Component.text("当前章节：", NamedTextColor.GOLD)
                    .append(Component.text(levelTitle, NamedTextColor.WHITE)));
        }

        for (JsonElement element : tasks) {
            if (element == null || !element.isJsonObject()) {
                continue;
            }
            renderTaskEntry(player, element.getAsJsonObject());
        }
    }

    private void renderTaskEntry(Player player, JsonObject task) {
        String title = safeLabel(getString(task, "title"));
        int progress = getInt(task, "progress", -1);
        int count = getInt(task, "count", -1);
        int remaining = getInt(task, "remaining", -1);

        player.sendMessage(Component.text("📘 任务：" + title, NamedTextColor.GOLD));

        JsonObject primaryMilestone = findPrimaryMilestone(task);
        String objective = deriveObjective(primaryMilestone, task);
        StringBuilder progressLine = new StringBuilder();
        if (primaryMilestone != null) {
            int msProgress = getInt(primaryMilestone, "progress", -1);
            int msCount = getInt(primaryMilestone, "count", -1);
            appendProgress(progressLine, msProgress, msCount);
            int msRemaining = getInt(primaryMilestone, "remaining", -1);
            if (msRemaining > 0) {
                if (progressLine.length() > 0) {
                    progressLine.append(" • ");
                }
                progressLine.append("剩余 ").append(msRemaining);
            }
        } else {
            appendProgress(progressLine, progress, count);
            if (remaining > 0) {
                if (progressLine.length() > 0) {
                    progressLine.append(" • ");
                }
                progressLine.append("剩余 ").append(remaining);
            }
        }

        String objectiveLine = joinNonEmpty(objective, progressLine.toString());
        if (objectiveLine != null && !objectiveLine.isBlank()) {
            player.sendMessage(Component.text("- 目标：" + objectiveLine, NamedTextColor.WHITE));
        }

        String hint = getString(task, "hint");
        if (hint != null && !hint.isBlank()) {
            player.sendMessage(Component.text("- 提示：" + hint, NamedTextColor.GRAY));
        }

        String rewardLine = formatReward(task);
        if (rewardLine != null && !rewardLine.isBlank()) {
            player.sendMessage(Component.text("- 奖励：" + rewardLine, NamedTextColor.YELLOW));
        }

        JsonArray milestones = getArray(task, "milestones");
        if (milestones != null && milestones.size() > 0) {
            for (JsonElement element : milestones) {
                if (element == null || !element.isJsonObject()) {
                    continue;
                }
                JsonObject milestone = element.getAsJsonObject();
                if (primaryMilestone != null && milestone == primaryMilestone) {
                    continue;
                }
                String status = getString(milestone, "status");
                if ("completed".equalsIgnoreCase(status)) {
                    continue;
                }
                String line = buildMilestoneLine(milestone);
                if (line != null) {
                    player.sendMessage(Component.text("- 阶段：" + line, NamedTextColor.AQUA));
                }
            }
        }
    }

    private void showMilestoneAction(Player player, String taskTitle, String milestoneTitle, int progress, int count) {
        StringBuilder message = new StringBuilder("★ 阶段完成：");
        if (milestoneTitle != null && !milestoneTitle.isBlank()) {
            message.append(milestoneTitle);
        } else if (taskTitle != null && !taskTitle.isBlank()) {
            message.append(taskTitle);
        } else {
            message.append("任务进度");
        }
        if (count > 0 && progress >= 0) {
            message.append(" (" + Math.min(progress, count) + "/" + count + ")");
        }
        player.sendActionBar(Component.text(message.toString(), NamedTextColor.LIGHT_PURPLE));
    }

    private JsonObject parseSnapshot(String payload) {
        try {
            JsonElement parsed = JsonParser.parseString(payload);
            if (!parsed.isJsonObject()) {
                return null;
            }
            JsonObject root = parsed.getAsJsonObject();
            if (root.has("active_tasks") && root.get("active_tasks").isJsonObject()) {
                return root.getAsJsonObject("active_tasks");
            }
            return null;
        } catch (Exception ex) {
            plugin.getLogger().log(Level.WARNING, "[QuestLogHud] failed to parse quest log payload", ex);
            return null;
        }
    }

    private JsonObject findPrimaryMilestone(JsonObject task) {
        JsonArray milestones = getArray(task, "milestones");
        if (milestones == null) {
            return null;
        }
        for (JsonElement element : milestones) {
            if (element == null || !element.isJsonObject()) {
                continue;
            }
            JsonObject milestone = element.getAsJsonObject();
            String status = getString(milestone, "status");
            if (!"completed".equalsIgnoreCase(status)) {
                return milestone;
            }
        }
        return null;
    }

    private String deriveObjective(JsonObject milestone, JsonObject task) {
        if (milestone != null) {
            String title = getString(milestone, "title");
            if (title != null && !title.isBlank()) {
                return title;
            }
        }
        String target = null;
        JsonElement targetEl = task.get("target");
        if (targetEl != null) {
            if (targetEl.isJsonPrimitive()) {
                target = targetEl.getAsString();
            } else if (targetEl.isJsonObject()) {
                JsonObject targetObj = targetEl.getAsJsonObject();
                target = getString(targetObj, "name");
                if ((target == null || target.isBlank()) && targetObj.has("type")
                        && targetObj.get("type").isJsonPrimitive()) {
                    target = targetObj.get("type").getAsString();
                }
            }
        }
        if (target != null && !target.isBlank()) {
            return target;
        }
        String hint = getString(task, "hint");
        if (hint != null && !hint.isBlank()) {
            return hint;
        }
        return safeLabel(getString(task, "title"));
    }

    private void appendProgress(StringBuilder builder, int progress, int count) {
        if (count <= 0 || progress < 0) {
            return;
        }
        if (builder.length() > 0) {
            builder.append(' ');
        }
        builder.append('(')
                .append(Math.min(progress, count))
                .append('/')
                .append(count)
                .append(')');
    }

    private String buildMilestoneLine(JsonObject milestone) {
        String title = safeLabel(getString(milestone, "title"));
        int progress = getInt(milestone, "progress", -1);
        int count = getInt(milestone, "count", -1);
        int remaining = getInt(milestone, "remaining", -1);

        List<String> segments = new ArrayList<>();
        if (!title.isBlank()) {
            segments.add(title);
        }
        if (count > 0 && progress >= 0) {
            segments.add("(" + Math.min(progress, count) + "/" + count + ")");
        }
        if (remaining > 0) {
            segments.add("剩余 " + remaining);
        }
        if (segments.isEmpty()) {
            return null;
        }
        return String.join(" ", segments);
    }

    private String formatReward(JsonObject task) {
        JsonObject reward = getObject(task, "reward");
        if (reward == null || reward.size() == 0) {
            return null;
        }
        if (reward.has("title") && reward.get("title").isJsonPrimitive()) {
            return reward.get("title").getAsString();
        }
        if (reward.has("name") && reward.get("name").isJsonPrimitive()) {
            return reward.get("name").getAsString();
        }
        if (reward.has("items") && reward.get("items").isJsonArray()) {
            JsonArray items = reward.getAsJsonArray("items");
            List<String> names = new ArrayList<>(items.size());
            for (JsonElement element : items) {
                if (element != null && element.isJsonPrimitive()) {
                    String value = element.getAsString();
                    if (value != null && !value.isBlank()) {
                        names.add(value);
                    }
                } else if (element != null && element.isJsonObject()) {
                    JsonObject obj = element.getAsJsonObject();
                    String value = getString(obj, "name");
                    if (value != null && !value.isBlank()) {
                        names.add(value);
                    }
                }
            }
            if (!names.isEmpty()) {
                return String.join(", ", names);
            }
        }
        Set<Map.Entry<String, JsonElement>> entries = reward.entrySet();
        if (!entries.isEmpty()) {
            List<String> fragments = new ArrayList<>();
            for (Map.Entry<String, JsonElement> entry : entries) {
                if (entry.getValue() != null && entry.getValue().isJsonPrimitive()) {
                    String value = entry.getValue().getAsString();
                    if (value != null && !value.isBlank()) {
                        fragments.add(entry.getKey() + ": " + value);
                    }
                }
            }
            if (!fragments.isEmpty()) {
                Collections.sort(fragments);
                return String.join(" · ", fragments);
            }
        }
        return null;
    }

    private JsonArray getArray(JsonObject obj, String key) {
        if (obj == null || key == null || !obj.has(key)) {
            return null;
        }
        JsonElement element = obj.get(key);
        if (element != null && element.isJsonArray()) {
            return element.getAsJsonArray();
        }
        return null;
    }

    private JsonObject getObject(JsonObject obj, String key) {
        if (obj == null || key == null || !obj.has(key)) {
            return null;
        }
        JsonElement element = obj.get(key);
        if (element != null && element.isJsonObject()) {
            return element.getAsJsonObject();
        }
        return null;
    }

    private String getString(JsonObject obj, String key) {
        if (obj == null || key == null || !obj.has(key)) {
            return null;
        }
        JsonElement element = obj.get(key);
        if (element == null || element.isJsonNull()) {
            return null;
        }
        if (element.isJsonPrimitive()) {
            return element.getAsJsonPrimitive().getAsString();
        }
        return null;
    }

    private int getInt(JsonObject obj, String key, int defaultValue) {
        if (obj == null || key == null || !obj.has(key)) {
            return defaultValue;
        }
        JsonElement element = obj.get(key);
        if (element == null || element.isJsonNull()) {
            return defaultValue;
        }
        if (element.isJsonPrimitive()) {
            JsonPrimitive primitive = element.getAsJsonPrimitive();
            if (primitive.isNumber()) {
                return primitive.getAsInt();
            }
            if (primitive.isString()) {
                try {
                    return Integer.parseInt(primitive.getAsString());
                } catch (NumberFormatException ignored) {
                    return defaultValue;
                }
            }
        }
        return defaultValue;
    }

    private String joinNonEmpty(String a, String b) {
        boolean hasA = a != null && !a.isBlank();
        boolean hasB = b != null && !b.isBlank();
        if (hasA && hasB) {
            return a + " " + b;
        }
        if (hasA) {
            return a;
        }
        if (hasB) {
            return b;
        }
        return null;
    }

    private String safeLabel(String source) {
        if (source == null || source.isBlank()) {
            return "未命名任务";
        }
        return source;
    }

    private String urlSegment(String text) {
        return URLEncoder.encode(text != null ? text : "", StandardCharsets.UTF_8);
    }
}

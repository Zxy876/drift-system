package com.driftmc.hud.dialogue;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.scene.RuleEventBridge;
import com.driftmc.story.LevelIds;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.TextComponent;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;

/**
 * ChoicePanel renders branching story options and emits rule events when players pick one.
 */
public final class ChoicePanel {

    private final JavaPlugin plugin;
    private final Map<UUID, ChoiceSession> sessions = new ConcurrentHashMap<>();
    private volatile RuleEventBridge ruleEvents;

    public ChoicePanel(JavaPlugin plugin) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
    }

    public void setRuleEventBridge(RuleEventBridge bridge) {
        this.ruleEvents = bridge;
    }

    /**
     * Show a choice node returned by the backend.
     */
    public void presentChoiceNode(Player player, JsonObject node) {
        if (player == null || node == null) {
            return;
        }
        JsonArray array = node.has("choices") && node.get("choices").isJsonArray()
                ? node.getAsJsonArray("choices")
                : null;
        if (array == null || array.size() == 0) {
            return;
        }

        List<ChoiceOption> options = parseOptions(array);
        if (options.isEmpty()) {
            return;
        }

        ChoiceSession session = new ChoiceSession(options, node);
        sessions.put(player.getUniqueId(), session);

        sendChoiceLayout(player, session, node);
    }

    /**
     * Handles chat text to see if it corresponds to a pending choice selection.
     */
    public boolean consumeSelection(Player player, String rawMessage) {
        if (player == null || rawMessage == null) {
            return false;
        }
        ChoiceSession session = sessions.get(player.getUniqueId());
        if (session == null) {
            return false;
        }
        String token = rawMessage.trim();
        if (token.isEmpty()) {
            return false;
        }

        ChoiceOption option = session.lookup(token);
        if (option == null) {
            return false;
        }

        Bukkit.getScheduler().runTask(plugin, () -> resolveSelection(player, session, option));
        return true;
    }

    public void clear(Player player) {
        if (player != null) {
            sessions.remove(player.getUniqueId());
        }
    }

    private void resolveSelection(Player player, ChoiceSession session, ChoiceOption option) {
        sessions.remove(player.getUniqueId());

        player.sendMessage(Component.text("你选择了: ", NamedTextColor.GRAY)
                .append(Component.text(option.label, NamedTextColor.GOLD)));

        RuleEventBridge bridge = this.ruleEvents;
        if (bridge != null && option.ruleEvent != null && !option.ruleEvent.isBlank()) {
            Map<String, Object> payload = new HashMap<>();
            payload.put("choice_id", option.id);
            payload.put("choice_label", option.label);
            payload.put("beat_id", session.getBeatId());
            payload.put("level_id", session.getLevelId());
            if (option.nextLevel != null) {
                payload.put("next_level", option.nextLevel);
            }
            if (!option.tags.isEmpty()) {
                payload.put("tags", new ArrayList<>(option.tags));
            }
            bridge.emit(player, option.ruleEvent, payload);
        }
    }

    private void sendChoiceLayout(Player player, ChoiceSession session, JsonObject node) {
        String title = safeText(node.get("title"));
        String prompt = safeText(node.get("prompt"));
        if (prompt.isEmpty()) {
            prompt = title.isEmpty() ? "请选择剧情分支" : title;
        }

        player.sendMessage(Component.text("━", NamedTextColor.DARK_GRAY)
                .append(Component.text(" 剧情分支 ", NamedTextColor.AQUA))
                .append(Component.text("━", NamedTextColor.DARK_GRAY)));
        player.sendMessage(Component.text(prompt, NamedTextColor.LIGHT_PURPLE));

        for (ChoiceOption option : session.options) {
            TextComponent.Builder line = Component.text()
                    .append(Component.text("[" + option.index + "] ", NamedTextColor.GOLD))
                    .append(Component.text(option.label, NamedTextColor.WHITE));
            if (option.ruleEvent != null && !option.ruleEvent.isBlank()) {
                line = line.hoverEvent(Component.text("点击填入选项", NamedTextColor.GREEN))
                        .clickEvent(ClickEvent.suggestCommand(Integer.toString(option.index)));
            }
            if (option.nextLevel != null && !option.nextLevel.isBlank()) {
                line = line.append(Component.text("  → " + option.nextLevel, NamedTextColor.GRAY));
            }
            player.sendMessage(line.build());
        }

        player.sendMessage(Component.text("输入序号或选项 ID 以继续。", NamedTextColor.GRAY));
    }

    private List<ChoiceOption> parseOptions(JsonArray array) {
        List<ChoiceOption> options = new ArrayList<>();
        int index = 0;

        for (JsonElement element : array) {
            if (!element.isJsonObject()) {
                continue;
            }
            JsonObject obj = element.getAsJsonObject();
            String id = safeText(obj.get("id"));
            if (id.isEmpty()) {
                id = safeText(obj.get("choice_id"));
            }
            if (id.isEmpty()) {
                id = "choice_" + (++index);
            } else {
                index++;
            }
            String label = safeText(obj.get("label"));
            if (label.isEmpty()) {
                label = safeText(obj.get("text"));
            }
            if (label.isEmpty()) {
                label = "选项 " + index;
            }
            String ruleEvent = safeText(obj.get("rule_event"));
            if (ruleEvent.isEmpty()) {
                ruleEvent = safeText(obj.get("event"));
            }
            String nextLevel = safeText(obj.get("next_level"));
            if (nextLevel.isEmpty()) {
                nextLevel = safeText(obj.get("next"));
            }
            nextLevel = LevelIds.canonicalizeLevelId(nextLevel);

            List<String> tags = new ArrayList<>();
            JsonElement tagNode = obj.get("tags");
            if (tagNode != null) {
                if (tagNode.isJsonArray()) {
                    for (JsonElement tagElement : tagNode.getAsJsonArray()) {
                        String tag = safeText(tagElement);
                        if (!tag.isEmpty()) {
                            tags.add(tag);
                        }
                    }
                } else {
                    String tag = safeText(tagNode);
                    if (!tag.isEmpty()) {
                        tags.add(tag);
                    }
                }
            }

            ChoiceOption option = new ChoiceOption(id, label, ruleEvent, index, nextLevel, tags);
            options.add(option);
        }
        return options;
    }

    private static String safeText(JsonElement element) {
        if (element == null || element.isJsonNull()) {
            return "";
        }
        return element.getAsString();
    }

    private static final class ChoiceSession {
        private final Map<String, ChoiceOption> tokenMap = new HashMap<>();
        private final List<ChoiceOption> options;
        private final String beatId;
        private final String levelId;

        ChoiceSession(List<ChoiceOption> options, JsonObject node) {
            this.options = options;
            this.beatId = safeText(node.get("beat_id"));
            this.levelId = LevelIds.canonicalizeLevelId(safeText(node.get("level_id")));
            indexTokens();
        }

        ChoiceOption lookup(String token) {
            if (token == null) {
                return null;
            }
            ChoiceOption option = tokenMap.get(token.trim());
            if (option != null) {
                return option;
            }
            String lowered = token.toLowerCase(Locale.ROOT).trim();
            return tokenMap.get(lowered);
        }

        private void indexTokens() {
            for (ChoiceOption option : options) {
                tokenMap.put(Integer.toString(option.index), option);
                if (option.id != null && !option.id.isBlank()) {
                    tokenMap.put(option.id, option);
                    tokenMap.put(option.id.toLowerCase(Locale.ROOT), option);
                }
                if (option.ruleEvent != null && !option.ruleEvent.isBlank()) {
                    tokenMap.put(option.ruleEvent, option);
                    tokenMap.put(option.ruleEvent.toLowerCase(Locale.ROOT), option);
                }
                if (option.label != null && !option.label.isBlank()) {
                    tokenMap.put(option.label, option);
                    tokenMap.put(option.label.toLowerCase(Locale.ROOT), option);
                }
            }
        }

        String getBeatId() {
            return beatId;
        }

        String getLevelId() {
            return levelId;
        }
    }

    private static final class ChoiceOption {
        final String id;
        final String label;
        final String ruleEvent;
        final int index;
        final String nextLevel;
        final List<String> tags;

        ChoiceOption(String id, String label, String ruleEvent, int index, String nextLevel, List<String> tags) {
            this.id = id;
            this.label = label;
            this.ruleEvent = ruleEvent;
            this.index = index;
            this.nextLevel = nextLevel;
            this.tags = tags;
        }
    }
}

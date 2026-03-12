package com.driftmc.hud.dialogue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.TextComponent;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.serializer.legacy.LegacyComponentSerializer;

/**
 * DialoguePanel renders structured NPC dialogue nodes with a light typing
 * effect.
 */
public final class DialoguePanel {

    private static final int LINE_INTERVAL_TICKS = 12; // ~0.6 seconds between lines
    private static final LegacyComponentSerializer LEGACY = LegacyComponentSerializer.legacySection();

    private final JavaPlugin plugin;
    private final ChoicePanel choicePanel;
    private final Map<UUID, List<Integer>> activeTasks = new ConcurrentHashMap<>();

    public DialoguePanel(JavaPlugin plugin, ChoicePanel choicePanel) {
        this.plugin = Objects.requireNonNull(plugin, "plugin");
        this.choicePanel = choicePanel;
    }

    public void clear(Player player) {
        if (player == null) {
            return;
        }
        clearScheduled(player);
        if (choicePanel != null) {
            choicePanel.clear(player);
        }
    }

    /**
     * Renders a dialogue node returned by the backend for the given player.
     */
    public void showDialogue(Player player, JsonObject node) {
        if (player == null || node == null || node.size() == 0) {
            return;
        }
        clearScheduled(player);
        if (choicePanel != null) {
            choicePanel.clear(player);
        }

        DialoguePayload payload = DialoguePayload.from(node);
        if (payload.lines.isEmpty() && payload.choices.isEmpty()) {
            return;
        }

        List<Integer> taskIds = new ArrayList<>();
        int delay = 0;

        if (payload.title != null) {
            Component header = Component.text(payload.title, NamedTextColor.LIGHT_PURPLE);
            int taskId = Bukkit.getScheduler().scheduleSyncDelayedTask(plugin,
                    () -> player.sendMessage(header),
                    delay);
            taskIds.add(taskId);
            delay += LINE_INTERVAL_TICKS;
        }

        for (Component line : payload.lines) {
            Component decorated = Component.text("❝ ", NamedTextColor.GRAY)
                    .append(line);
            int taskId = Bukkit.getScheduler().scheduleSyncDelayedTask(plugin,
                    () -> player.sendMessage(decorated),
                    delay);
            taskIds.add(taskId);
            delay += LINE_INTERVAL_TICKS;
        }

        boolean hasChoiceArray = node.has("choices") && node.get("choices").isJsonArray()
                && node.getAsJsonArray("choices").size() > 0;

        if (hasChoiceArray && choicePanel != null) {
            int taskId = Bukkit.getScheduler().scheduleSyncDelayedTask(plugin,
                    () -> choicePanel.presentChoiceNode(player, node),
                    delay);
            taskIds.add(taskId);
        } else if (!payload.choices.isEmpty()) {
            int taskId = Bukkit.getScheduler().scheduleSyncDelayedTask(plugin,
                    () -> renderChoices(player, payload.choices),
                    delay);
            taskIds.add(taskId);
        }

        if (!taskIds.isEmpty()) {
            activeTasks.put(player.getUniqueId(), taskIds);
        }
    }

    private void renderChoices(Player player, List<Choice> choices) {
        player.sendMessage(Component.text("—").color(NamedTextColor.DARK_GRAY));
        player.sendMessage(Component.text("请选择对话选项：", NamedTextColor.AQUA));

        for (int i = 0; i < choices.size(); i++) {
            Choice choice = choices.get(i);
            int index = i + 1;
            TextComponent.Builder line = Component.text()
                    .append(Component.text(index + ". ", NamedTextColor.GOLD))
                    .append(choice.label);
            if (choice.command != null) {
                line.hoverEvent(Component.text("点击选择该选项", NamedTextColor.GREEN))
                        .clickEvent(ClickEvent.runCommand(choice.command));
            }
            player.sendMessage(line.build());
        }

        if (!choices.isEmpty() && choices.stream().noneMatch(choice -> choice.command != null)) {
            player.sendMessage(Component.text("提示：输入序号即可继续，例如 1", NamedTextColor.GRAY));
        }
    }

    private void clearScheduled(Player player) {
        UUID playerId = player.getUniqueId();
        List<Integer> ids = activeTasks.remove(playerId);
        if (ids == null) {
            return;
        }
        for (int id : ids) {
            Bukkit.getScheduler().cancelTask(id);
        }
    }

    // ---------------------------------------------------------------------
    // Payload parsing helpers
    // ---------------------------------------------------------------------
    private static final class DialoguePayload {
        @SuppressWarnings("Immutable")
        final List<Component> lines;
        final List<Choice> choices;
        final String title;

        private DialoguePayload(String title, List<Component> lines, List<Choice> choices) {
            this.title = title;
            this.lines = lines;
            this.choices = choices;
        }

        static DialoguePayload from(JsonObject node) {
            String title = safeText(node.get("title"));
            List<Component> lines = new ArrayList<>();

            // Prefer explicit script array, otherwise split textual body.
            if (node.has("script") && node.get("script").isJsonArray()) {
                JsonArray script = node.getAsJsonArray("script");
                for (JsonElement element : script) {
                    String rendered = renderScriptLine(element);
                    if (!rendered.isBlank()) {
                        lines.add(LEGACY.deserialize(rendered));
                    }
                }
            } else {
                String text = safeText(node.get("text"));
                if (!text.isBlank()) {
                    for (String rawLine : text.split("\\r?\\n")) {
                        String trimmed = rawLine.trim();
                        if (!trimmed.isEmpty()) {
                            lines.add(LEGACY.deserialize(trimmed));
                        }
                    }
                }
            }

            List<Choice> choices = parseChoices(node.get("choices"));
            return new DialoguePayload(title, lines, choices);
        }

        private static String renderScriptLine(JsonElement element) {
            if (element == null || element.isJsonNull()) {
                return "";
            }
            if (element.isJsonObject()) {
                JsonObject obj = element.getAsJsonObject();
                String op = safeText(obj.get("op"));
                if ("npc_say".equalsIgnoreCase(op)) {
                    String speaker = safeText(obj.get("npc"));
                    String text = safeText(obj.get("text"));
                    if (!text.isBlank()) {
                        if (!speaker.isBlank()) {
                            return "§d[" + speaker + "]§r " + text;
                        }
                        return text;
                    }
                }
                if ("narrate".equalsIgnoreCase(op)) {
                    String text = safeText(obj.get("text"));
                    if (!text.isBlank()) {
                        return "§7" + text;
                    }
                }
            }
            return element.getAsString();
        }

        private static List<Choice> parseChoices(JsonElement element) {
            if (!(element instanceof JsonArray array) || array.size() == 0) {
                return Collections.emptyList();
            }
            List<Choice> choices = new ArrayList<>();
            for (JsonElement entry : array) {
                if (!entry.isJsonObject()) {
                    continue;
                }
                JsonObject obj = entry.getAsJsonObject();
                String label = safeText(obj.get("label"));
                if (label.isBlank()) {
                    continue;
                }
                Component labelComponent = LEGACY.deserialize(label);
                String command = safeText(obj.get("command"));
                if (command.isBlank()) {
                    command = null;
                }
                choices.add(new Choice(labelComponent, command));
            }
            return choices;
        }

        private static String safeText(JsonElement element) {
            if (element == null || element.isJsonNull()) {
                return "";
            }
            return element.getAsString();
        }
    }

    private record Choice(Component label, String command) {
    }
}

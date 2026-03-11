package com.driftmc.commands;

import java.lang.reflect.Type;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.driftmc.intent.IntentRouter;
import com.driftmc.session.PlayerSessionManager;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

/**
 * /advance <自然语言>
 * 手动推进一次 StoryEngine（相当于「说一句话」）
 */
public class AdvanceCommand implements CommandExecutor {

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public AdvanceCommand(
            JavaPlugin plugin,
            BackendClient backend,
            IntentRouter router,
            WorldPatchExecutor world,
            PlayerSessionManager sessions) {
        this.plugin = plugin;
        this.backend = backend;
        this.router = router;
        this.world = world;
        this.sessions = sessions;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage(ChatColor.RED + "只有玩家可以推进心悦故事~");
            return true;
        }

        String content;
        if (args.length == 0) {
            content = "继续";
        } else {
            content = String.join(" ", args);
        }

        player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 你向心悦世界轻声说：“"
                + ChatColor.WHITE + content + ChatColor.LIGHT_PURPLE + "”");

        UUID playerUuid = player.getUniqueId();
        String playerId = player.getName();

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                Map<String, Object> bodyMap = new HashMap<>();
                bodyMap.put("player_id", playerId);
                bodyMap.put("world_state", new HashMap<>());
                Map<String, Object> action = new HashMap<>();
                action.put("say", content);
                bodyMap.put("action", action);
                String body = GSON.toJson(bodyMap);

                String resp = backend.postJson("/story/advance", body);

                Bukkit.getScheduler().runTask(plugin, () -> handleSuccess(playerUuid, resp));

            } catch (Exception e) {
                Bukkit.getScheduler().runTask(plugin, () -> handleFailure(playerUuid, e));
            }
        });

        return true;
    }

    private void handleSuccess(UUID playerUuid, String resp) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }

        String nodeText = extractNodeText(resp);
        if (nodeText != null && !nodeText.isEmpty()) {
            player.sendMessage(ChatColor.AQUA + "【故事】 " + ChatColor.WHITE + nodeText);
        }

        applyPatchFromResponse(player, resp);
    }

    private void handleFailure(UUID playerUuid, Exception error) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }
        player.sendMessage(ChatColor.RED + "❌ 推进失败: " + error.getMessage());
    }

    private String extractNodeText(String resp) {
        try {
            JsonObject root = JsonParser.parseString(resp).getAsJsonObject();
            if (!root.has("node") || !root.get("node").isJsonObject()) return null;
            JsonObject node = root.getAsJsonObject("node");
                
            if (node.has("text") && node.get("text").isJsonPrimitive()) {
                return node.get("text").getAsString();
            }
        } catch (Exception ignored) {}
        return null;
        
    }

    @SuppressWarnings("unchecked")
    private void applyPatchFromResponse(Player player, String resp) {
        try {
            JsonElement rootEl = JsonParser.parseString(resp);
            if (!rootEl.isJsonObject()) return;

                
            JsonObject root = rootEl.getAsJsonObject();
            if (!root.has("world_patch") || !root.get("world_patch").isJsonObject()) {
                return;
            }

            JsonObject patchObj = root.getAsJsonObject("world_patch");
            Type type = new TypeToken<Map<String, Object>>() {}.getType();
            Map<String, Object> patch = GSON.fromJson(patchObj
            , type);
            if (patch == null || patch.isEmpty()) return;

                
            Object mcObj = patch.get("mc");
            Map<String, Object> mcPatch;
            if (mcObj instanceof Map<?, ?> m) {
                mcPatch = (Map<String, Object>) m;
            } else {
                mcPatch = patch;
            }

            world.execute(player, mcPatch);

        } catch (Exception ignored) {}
    }
        
}
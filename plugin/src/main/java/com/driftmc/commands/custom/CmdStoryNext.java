package com.driftmc.commands.custom;

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
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

/**
 * /storynext
 * 相当于对 StoryEngine 说了一句「继续」。
 */
public class CmdStoryNext implements CommandExecutor {

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    private final WorldPatchExecutor world;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public CmdStoryNext(
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
            sender.sendMessage(ChatColor.RED + "只有玩家可以推进故事~");
            return true;
        }

        String playerId = player.getName();
        player.sendMessage(ChatColor.LIGHT_PURPLE + "✧ 故事轻轻向前滑了一格 ……");

        UUID playerUuid = player.getUniqueId();

        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                Map<String, Object> bodyMap = new HashMap<>();
                bodyMap.put("player_id", playerId);
                bodyMap.put("world_state", new HashMap<>());
                Map<String, Object> action = new HashMap<>();
                action.put("say", "继续");
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

        try {
            JsonObject root = JsonParser.parseString(resp).getAsJsonObject();
            if (root.has("node") && root.get("node").isJsonObject()) {
                JsonObject node = root.getAsJsonObject("node");
                String title = node.has("title") ? node.get("title").getAsString() : "";
                String text = node.has("text") ? node.get("text").getAsString() : "";
                if (!title.isEmpty()) {
                    player.sendMessage(ChatColor.AQUA + "【" + title + "】");
                }
                if (!text.isEmpty()) {
                    player.sendMessage(ChatColor.WHITE + text);
                }
            }

            if (root.has("world_patch") && root.get("world_patch").isJsonObject()) {
                var patchObj = root.getAsJsonObject("world_patch");
                Type type = new TypeToken<Map<String, Object>>() {
                }.getType();
                Map<String, Object> patch = GSON.fromJson(patchObj, type);
                if (patch != null && !patch.isEmpty()) {
                    Object mcObj = patch.get("mc");
                    @SuppressWarnings("unchecked")
                    Map<String, Object> mcPatch = (mcObj instanceof Map)
                            ? (Map<String, Object>) mcObj
                            : patch;
                    world.execute(player, mcPatch);
                }
            }

        } catch (Exception parseError) {
            player.sendMessage(ChatColor.RED + "❌ 故事推进失败: " + parseError.getMessage());
        }
    }

    private void handleFailure(UUID playerUuid, Exception error) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }
        player.sendMessage(ChatColor.RED + "❌ 故事推进失败: " + error.getMessage());
    }
}
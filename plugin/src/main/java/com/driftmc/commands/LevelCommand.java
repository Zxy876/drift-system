package com.driftmc.commands;

import java.lang.reflect.Type;
import java.util.LinkedHashMap;
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
import com.driftmc.story.LevelIds;
import com.driftmc.world.PayloadExecutorV1;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;

/**
 * /level <level_id>
 * 调用后端：/story/load
 */
public class LevelCommand implements CommandExecutor {

    private static final Gson GSON = new Gson();

    private final JavaPlugin plugin;
    private final BackendClient backend;
    @SuppressWarnings("unused")
    private final IntentRouter router;
    private final WorldPatchExecutor world;
    private final PayloadExecutorV1 payloadExecutor;
    @SuppressWarnings("unused")
    private final PlayerSessionManager sessions;

    public LevelCommand(
            JavaPlugin plugin,
            BackendClient backend,
            IntentRouter router,
            WorldPatchExecutor world,
            PayloadExecutorV1 payloadExecutor,
            PlayerSessionManager sessions) {
        this.plugin = plugin;
        this.backend = backend;
        this.router = router;
        this.world = world;
        this.payloadExecutor = payloadExecutor;
        this.sessions = sessions;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage(ChatColor.RED + "只有玩家可以加载心悦关卡~");
            return true;
        }

        if (args.length != 1) {
            player.sendMessage(ChatColor.RED + "用法: /level <level_id>");
            return true;
        }

        String requestedLevel = args[0];
        String levelId = LevelIds.canonicalizeOrDefault(requestedLevel);
        String playerId = player.getName();

        if (sessions != null
                && LevelIds.isFlagshipTutorial(levelId)
                && sessions.hasCompletedTutorial(player)) {
            player.sendMessage(ChatColor.GOLD + "教程已完成，正为你打开心湖枢纽入口。");
            Map<String, Object> mcPatch = new LinkedHashMap<>();
            Map<String, Object> teleport = new LinkedHashMap<>();
            teleport.put("mode", "absolute");
            teleport.put("world", "KunmingLakeHub");
            teleport.put("x", 128.5D);
            teleport.put("y", 72.0D);
            teleport.put("z", -16.5D);
            teleport.put("yaw", 180.0D);
            teleport.put("pitch", 0.0D);
            mcPatch.put("teleport", teleport);
            mcPatch.put("tell", "§e教程完成§r，欢迎回到心湖枢纽探索主线章节。");
            world.execute(player, mcPatch);
            return true;
        }

        player.sendMessage(ChatColor.YELLOW + "📘 正在为 "
                + ChatColor.AQUA + playerId
                + ChatColor.YELLOW + " 加载关卡: "
                + ChatColor.GOLD + levelId);
        if (!levelId.equals(requestedLevel)) {
            player.sendMessage(ChatColor.GRAY + "(使用别名 " + requestedLevel + " → " + levelId + ")");
        }

        UUID playerUuid = player.getUniqueId();
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                Map<String, Object> bodyMap = new LinkedHashMap<>();
                bodyMap.put("player_id", playerId);
                bodyMap.put("level_id", levelId);
                String resp = backend.postJson("/story/load", GSON.toJson(bodyMap));
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

        applyPatchFromResponse(player, resp, true);

        String msg = extractMsg(resp);
        if (msg == null || msg.isEmpty()) {
            msg = "关卡已加载，欢迎来到心悦宇宙的这一章。";
        }

        player.sendMessage(ChatColor.GREEN + "✔ " + msg);
    }

    private void handleFailure(UUID playerUuid, Exception error) {
        Player player = Bukkit.getPlayer(playerUuid);
        if (player == null || !player.isOnline()) {
            return;
        }
        player.sendMessage(ChatColor.RED + "❌ 加载关卡失败: " + error.getMessage());
    }

    // ------------ JSON 帮助 ------------

    private String extractMsg(String resp) {
        try {
            JsonObject root = JsonParser.parseString(resp).getAsJsonObject();
            if (root.has("msg") && root.get("msg").isJsonPrimitive()) {
                return root.get("msg").getAsString();
            }
        } catch (Exception ignored) {
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    private void applyPatchFromResponse(Player player, String resp, boolean useBootstrap) {
        try {
                
            JsonElement rootEl = JsonParser.parseString(resp);
            if (!rootEl.isJsonObject()) return;

            JsonObject root = rootEl.getAsJsonObject();
            JsonObject patchObj = null;

            if (useBootstrap && root.has("bootstrap_patch") && root.get("bootstrap_patch").isJsonObject()) {
                patchObj = root.getAsJsonObject("bootstrap_patch");
            } else if (root.has("world_patch") && root.get("world_patch").isJsonObject()) {
                patchObj = root.getAsJsonObject("world_patch");
            }
                

            if (patchObj == null) return;

            if (isPayloadV1(patchObj)) {
                boolean accepted = payloadExecutor != null && payloadExecutor.enqueue(player, patchObj);
                if (!accepted) {
                    player.sendMessage(ChatColor.RED + "❌ 关卡 payload 入队失败，请稍后重试或使用 /taskdebug。");
                }
                return;
            }
            

            Type type = new TypeToken<Map<String,
                Object>>() {}.getType();
            Map<String, Object> patch = GSON.fromJson(patchObj, type);
            if (patch == null || patch.isEmpty()) return;

            Object mcObj = patch.get("mc");
            Map<String, Object> mcPatch;
            if (mcObj instanceof Map<?, ?> m) {
                mcPatch = (Map<String, Object>) m;
            } else {
                mcPatch = patch;
            }

            world.execute(player, mcPatch);

        } catch (Exception ignored) {
        }
    }

    private boolean isPayloadV1(JsonObject obj) {
        return obj != null
                && obj.has("version")
                && obj.get("version").isJsonPrimitive()
                && "plugin_payload_v1".equals(obj.get("version").getAsString());
    }
}
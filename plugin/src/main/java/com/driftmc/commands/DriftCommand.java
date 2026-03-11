package com.driftmc.commands;

import java.io.IOException;
import java.util.Locale;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.backend.BackendClient;
import com.driftmc.story.StoryManager;
import com.driftmc.tutorial.TutorialManager;
import com.driftmc.world.WorldPatchExecutor;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonSyntaxException;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;
import okhttp3.ResponseBody;

/**
 * DriftCommand - 主命令处理器
 * 
 * 提供手动命令接口（虽然主要是自然语言驱动）
 * 
 * 命令:
 * /drift status - 查看云端连接状态
 * /drift levels - 查看可用关卡
 * /drift load <level_id> - 加载关卡
 * /drift spawn - 生成场景片段
 * /drift sync - 同步剧情状态
 * /drift debug - 调试信息
 * /drift report - 查看最近执行回传
 * /drift where - 查看当前位置与锚点距离
 * /drift goto - 传送到固定锚点
 * /drift tutorial - 教学系统相关命令
 */
public class DriftCommand implements CommandExecutor {

  private final BackendClient backend;
  private final StoryManager storyManager;
  private final WorldPatchExecutor worldPatcher;
  private final TutorialManager tutorialManager;

  public DriftCommand(
      BackendClient backend,
      StoryManager storyManager,
      WorldPatchExecutor worldPatcher,
      TutorialManager tutorialManager) {
    this.backend = backend;
    this.storyManager = storyManager;
    this.worldPatcher = worldPatcher;
    this.tutorialManager = tutorialManager;
  }

  @Override
  public boolean onCommand(
      CommandSender sender,
      Command command,
      String label,
      String[] args) {
    if (!(sender instanceof Player)) {
      sender.sendMessage("§c只有玩家可以使用此命令");
      return true;
    }

    Player player = (Player) sender;

    if (args.length == 0) {
      showHelp(player);
      return true;
    }

    switch (args[0].toLowerCase()) {
      case "status":
        showStatus(player);
        break;

      case "levels":
        dispatchAsPlayer(player, "levels");
        break;

      case "load":
        if (args.length < 2 || args[1].isBlank()) {
          player.sendMessage("§c用法: /drift load <level_id>");
          break;
        }
        dispatchAsPlayer(player, "level " + args[1]);
        break;

      case "spawn":
        dispatchAsPlayer(player, "spawnfragment");
        break;

      case "sync":
        syncState(player);
        break;

      case "debug":
        showDebug(player);
        break;

      case "report":
        showApplyReport(player);
        break;

      case "where":
        showWhere(player);
        break;

      case "goto":
        gotoAnchor(player);
        break;

      case "tutorial":
        handleTutorial(player, args);
        break;

      default:
        showHelp(player);
    }

    return true;
  }

  private void showHelp(Player player) {
    player.sendMessage("§b========== Drift System ==========");
    player.sendMessage("§7直接在聊天中说话即可与系统交互！");
    player.sendMessage("");
    player.sendMessage("§e手动命令:");
    player.sendMessage("  §f/drift status §7- 查看云端状态");
    player.sendMessage("  §f/drift levels §7- 查看可用关卡");
    player.sendMessage("  §f/drift load <id> §7- 加载指定关卡");
    player.sendMessage("  §f/drift spawn §7- 生成场景片段");
    player.sendMessage("  §f/drift sync §7- 同步剧情状态");
    player.sendMessage("  §f/drift debug §7- 显示调试信息");
    player.sendMessage("  §f/drift report §7- 显示最近执行回传");
    player.sendMessage("  §f/drift where §7- 显示你与锚点距离");
    player.sendMessage("  §f/drift goto §7- 传送到固定锚点");
    player.sendMessage("  §f/drift tutorial §7- 教学系统");
    player.sendMessage("    §f/drift tutorial start §7- 开始教学");
    player.sendMessage("    §f/drift tutorial hint §7- 获取提示");
    player.sendMessage("    §f/drift tutorial skip §7- 跳过教学");
    player.sendMessage("§b================================");
  }

  private void handleTutorial(Player player, String[] args) {
    if (args.length < 2) {
      player.sendMessage("§e教学命令:");
      player.sendMessage("  §f/drift tutorial start §7- 开始/重新开始教学");
      player.sendMessage("  §f/drift tutorial hint §7- 获取当前步骤提示");
      player.sendMessage("  §f/drift tutorial skip §7- 跳过教学");
      return;
    }

    switch (args[1].toLowerCase()) {
      case "start":
        tutorialManager.startTutorial(player);
        break;

      case "hint":
        tutorialManager.getHint(player);
        break;

      case "skip":
        player.sendMessage("§e确定要跳过教学吗？(输入 /drift tutorial skip confirm)");
        if (args.length >= 3 && "confirm".equalsIgnoreCase(args[2])) {
          tutorialManager.skipTutorial(player);
        }
        break;

      default:
        player.sendMessage("§c未知的教学命令");
    }
  }

  private void showStatus(Player player) {
    String payloadVersion = readEnv("PAYLOAD_VERSION", "v2");
    String backendUrl = backend.getBaseUrl();

    player.sendMessage("§b========== Drift System Status ==========");
    player.sendMessage("§7Backend: §eChecking...");
    player.sendMessage("§7URL: §f" + backendUrl);
    player.sendMessage("§7Story Engine: §aActive");
    player.sendMessage("§7Payload: §a" + payloadVersion);

    backend.getAsync("/health", new Callback() {
      @Override
      public void onFailure(Call call, IOException e) {
        Bukkit.getScheduler().runTask(worldPatcher.getPlugin(),
            () -> player.sendMessage("§7Backend: §cDisconnected"));
      }

      @Override
      public void onResponse(Call call, Response response) throws IOException {
        int statusCode = response.code();
        String body = "";
        try (response) {
          ResponseBody responseBody = response.body();
          if (responseBody != null) {
            body = responseBody.string();
          }
        }

        boolean connected = statusCode >= 200 && statusCode < 300 && isHealthOk(body);
        Bukkit.getScheduler().runTask(worldPatcher.getPlugin(), () -> {
          if (connected) {
            player.sendMessage("§7Backend: §aConnected");
          } else {
            player.sendMessage("§7Backend: §cDisconnected");
          }
        });
      }
    });

    StoryManager.StoryState state = storyManager.getState(player);
    player.sendMessage("§7Current Level: §f" + storyManager.getCurrentLevel(player));
    player.sendMessage("§7Node Index: §f" + state.getNodeIndex());
    player.sendMessage("§b========================================");
  }

  private void syncState(Player player) {
    player.sendMessage("§e正在同步剧情状态...");
    storyManager.syncState(player, () -> {
      player.sendMessage("§a同步完成！");
      showStatus(player);
    });
  }

  private void showDebug(Player player) {
    player.sendMessage("§b========== 调试信息 ==========");
    player.sendMessage("§7玩家: §f" + player.getName());
    player.sendMessage("§7UUID: §f" + player.getUniqueId());
    player.sendMessage("§7位置: §f" +
        String.format("%.1f, %.1f, %.1f",
            player.getLocation().getX(),
            player.getLocation().getY(),
            player.getLocation().getZ()));
    player.sendMessage("§7世界: §f" + player.getWorld().getName());
    player.sendMessage("§b============================");
  }

  private void showApplyReport(Player player) {
    String path = "/world/story/" + player.getName() + "/debug/tasks";
    backend.getAsync(path, new Callback() {
      @Override
      public void onFailure(Call call, IOException e) {
        Bukkit.getScheduler().runTask(worldPatcher.getPlugin(),
            () -> player.sendMessage("§c[report] 拉取失败: " + e.getMessage()));
      }

      @Override
      public void onResponse(Call call, Response response) throws IOException {
        int code = response.code();
        String body;
        try (response) {
          ResponseBody responseBody = response.body();
          body = responseBody != null ? responseBody.string() : "{}";
        }

        Bukkit.getScheduler().runTask(worldPatcher.getPlugin(), () -> renderApplyReport(player, code, body));
      }
    });
  }

  private void renderApplyReport(Player player, int statusCode, String body) {
    if (statusCode < 200 || statusCode >= 300) {
      player.sendMessage("§c[report] 接口异常: HTTP " + statusCode);
      return;
    }

    JsonObject root;
    try {
      root = JsonParser.parseString(body).getAsJsonObject();
    } catch (Exception ex) {
      player.sendMessage("§c[report] 返回不是有效 JSON");
      return;
    }

    JsonObject report = root.has("last_apply_report") && root.get("last_apply_report").isJsonObject()
        ? root.getAsJsonObject("last_apply_report")
        : null;

    if (report == null) {
      player.sendMessage("§e[report] 暂无 last_apply_report（还未执行 payload 或无回传）");
      return;
    }

    player.sendMessage("§b========== 执行回传 ==========");
    player.sendMessage("§7build_id: §f" + getString(report, "build_id", "unknown"));
    player.sendMessage("§7last_status: §f" + getString(report, "last_status", "unknown"));
    player.sendMessage("§7last_failure_code: §f" + getString(report, "last_failure_code", "NONE"));
    player.sendMessage("§7last_executed: §f" + getString(report, "last_executed", "0"));
    player.sendMessage("§7last_failed: §f" + getString(report, "last_failed", "0"));
    player.sendMessage("§7last_duration_ms: §f" + getString(report, "last_duration_ms", "0"));
    player.sendMessage("§7fallback: §f"
        + getString(root, "last_fallback_flag", "false")
        + " §7reason: §f"
        + getString(root, "last_fallback_reason", "none"));
    player.sendMessage("§b==============================");
  }

  private void showWhere(Player player) {
    int baseX = readEnvInt("DRIFT_FIXED_ANCHOR_X", 0);
    int baseY = readEnvInt("DRIFT_FIXED_ANCHOR_Y", 64);
    int baseZ = readEnvInt("DRIFT_FIXED_ANCHOR_Z", 0);

    Location loc = player.getLocation();
    double dx = loc.getX() - baseX;
    double dy = loc.getY() - baseY;
    double dz = loc.getZ() - baseZ;
    double distance = Math.sqrt(dx * dx + dy * dy + dz * dz);

    player.sendMessage("§b========== 空间定位 ==========");
    player.sendMessage("§7player: §f" + String.format("%.2f, %.2f, %.2f", loc.getX(), loc.getY(), loc.getZ()));
    player.sendMessage("§7origin(fixed): §f" + baseX + ", " + baseY + ", " + baseZ);
    player.sendMessage("§7distance: §f" + String.format("%.2f", distance));
    player.sendMessage("§7提示: §f/drift report 查看最近 build 执行状态");
    player.sendMessage("§b==============================");
  }

  private void gotoAnchor(Player player) {
    int baseX = readEnvInt("DRIFT_FIXED_ANCHOR_X", 0);
    int baseY = readEnvInt("DRIFT_FIXED_ANCHOR_Y", 64);
    int baseZ = readEnvInt("DRIFT_FIXED_ANCHOR_Z", 0);

    Location target = new Location(
        player.getWorld(),
        baseX + 0.5,
        baseY + 1.2,
        baseZ + 0.5,
        player.getLocation().getYaw(),
        player.getLocation().getPitch());

    boolean ok = player.teleport(target);
    if (ok) {
      player.sendMessage("§a已传送到锚点: §f(" + baseX + ", " + baseY + ", " + baseZ + ")");
    } else {
      player.sendMessage("§c传送失败，请稍后重试。");
    }
  }

  private int readEnvInt(String key, int defaultValue) {
    try {
      String raw = System.getenv(key);
      if (raw == null || raw.isBlank()) {
        return defaultValue;
      }
      return Integer.parseInt(raw.trim());
    } catch (Exception ex) {
      return defaultValue;
    }
  }

  private String readEnv(String key, String defaultValue) {
    String raw = System.getenv(key);
    if (raw == null || raw.isBlank()) {
      return defaultValue;
    }
    return raw.trim();
  }

  private boolean isHealthOk(String body) {
    if (body == null || body.isBlank()) {
      return false;
    }
    try {
      JsonObject root = JsonParser.parseString(body).getAsJsonObject();
      String status = getString(root, "status", "");
      return "ok".equalsIgnoreCase(status);
    } catch (JsonSyntaxException | IllegalStateException ex) {
      String normalized = body.toLowerCase(Locale.ROOT);
      return normalized.contains("\"status\"") && normalized.contains("\"ok\"");
    }
  }

  private void dispatchAsPlayer(Player player, String commandLine) {
    boolean accepted = Bukkit.dispatchCommand(player, commandLine);
    if (!accepted) {
      player.sendMessage("§c命令执行失败: /" + commandLine);
    }
  }

  private String getString(JsonObject obj, String key, String fallback) {
    if (obj == null || !obj.has(key) || obj.get(key).isJsonNull()) {
      return fallback;
    }
    try {
      return obj.get(key).getAsString();
    } catch (Exception ex) {
      return fallback;
    }
  }
}

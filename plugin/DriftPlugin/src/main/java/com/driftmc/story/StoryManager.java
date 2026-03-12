package com.driftmc.story;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.plugin.Plugin;

import com.driftmc.backend.BackendClient;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

/**
 * StoryManager - 管理玩家的剧情状态
 * 
 * 功能:
 * 1. 跟踪每个玩家当前所在的关卡
 * 2. 提供剧情推进/回退能力
 * 3. 管理剧情分支选择
 */
public class StoryManager {

  private final Plugin plugin;
  private final BackendClient backend;
  private final Gson gson = new Gson();

  // 玩家UUID -> 当前关卡ID
  private final Map<UUID, String> playerLevels = new HashMap<>();

  // 玩家UUID -> 剧情状态
  private final Map<UUID, StoryState> playerStates = new HashMap<>();

  public StoryManager(Plugin plugin, BackendClient backend) {
    this.plugin = plugin;
    this.backend = backend;
  }

  /**
   * 获取玩家当前关卡
   */
  public String getCurrentLevel(Player player) {
    String stored = playerLevels.get(player.getUniqueId());
    if (stored == null || stored.isBlank()) {
      return LevelIds.DEFAULT_LEVEL;
    }
    return LevelIds.canonicalizeLevelId(stored);
  }

  /**
   * 设置玩家当前关卡
   */
  public void setCurrentLevel(Player player, String levelId) {
    playerLevels.put(player.getUniqueId(), LevelIds.canonicalizeOrDefault(levelId));
  }

  /**
   * 获取玩家剧情状态
   */
  public StoryState getState(Player player) {
    return playerStates.computeIfAbsent(
        player.getUniqueId(),
        k -> new StoryState());
  }

  /**
   * 从后端同步玩家状态
   */
  public void syncState(Player player, Runnable onSuccess) {
    backend.postJsonAsync(
        "/story/state/" + player.getName(),
        "{}",
        new Callback() {
          @Override
          public void onFailure(Call call, IOException e) {
            plugin.getLogger().warning(
                "[StoryManager] 同步状态失败: " + e.getMessage());
          }

          @Override
          public void onResponse(Call call, Response response) throws IOException {
            try (response) {
              String json = response.body() != null ? response.body().string() : "{}";
              JsonObject root = JsonParser.parseString(json)
                  .getAsJsonObject();

              if (root.has("state") && root.get("state").isJsonObject()) {
                JsonObject state = root.getAsJsonObject("state");

                // 更新本地状态
                if (state.has("current_level")) {
                  String level = state.get("current_level").getAsString();
                  setCurrentLevel(player, level);
                }
              }

              if (onSuccess != null) {
                Bukkit.getScheduler().runTask(plugin, onSuccess);
              }
            }
          }
        });
  }

  /**
   * 剧情状态类
   */
  public static class StoryState {
    private int nodeIndex = 0;
    private boolean canAdvance = true;
    private String lastChoice = null;

    public int getNodeIndex() {
      return nodeIndex;
    }

    public void setNodeIndex(int index) {
      this.nodeIndex = index;
    }

    public boolean canAdvance() {
      return canAdvance;
    }

    public void setCanAdvance(boolean can) {
      this.canAdvance = can;
    }

    public String getLastChoice() {
      return lastChoice;
    }

    public void setLastChoice(String choice) {
      this.lastChoice = choice;
    }
  }
}

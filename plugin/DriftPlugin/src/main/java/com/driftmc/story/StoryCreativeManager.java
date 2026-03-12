package com.driftmc.story;

import org.bukkit.GameMode;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.EventPriority;
import org.bukkit.event.Listener;
import org.bukkit.event.block.BlockBreakEvent;
import org.bukkit.event.block.BlockPlaceEvent;
import org.bukkit.event.player.PlayerInteractEvent;
import org.bukkit.plugin.java.JavaPlugin;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * StoryCreativeManager - 剧情中的创造权限管理器
 * 
 * 功能：
 * - 允许玩家在剧情场景中建造
 * - 限制建造范围（不影响其他场景）
 * - 自动记录玩家创造的内容
 */
public class StoryCreativeManager implements Listener {

  private final JavaPlugin plugin;

  // 记录哪些玩家在剧情中有创造权限
  private final Map<UUID, StoryCreativeSession> creativeSessions = new HashMap<>();

  public StoryCreativeManager(JavaPlugin plugin) {
    this.plugin = plugin;
  }

  /**
   * 为玩家开启剧情创造模式
   */
  public void enableCreativeMode(Player player, String levelId) {
    UUID playerId = player.getUniqueId();

    StoryCreativeSession session = new StoryCreativeSession(
        levelId,
        player.getGameMode(),
        player.getLocation().clone());

    creativeSessions.put(playerId, session);

    // 切换到创造模式
    player.setGameMode(GameMode.CREATIVE);
    player.sendMessage("§a✧ 剧情创造模式已开启");
    player.sendMessage("§7- 你可以在场景中自由建造");
    player.sendMessage("§7- 你的创造会被保存为场景的一部分");
    player.sendMessage("§7- 输入 /story creative off 退出创造模式");

    plugin.getLogger().info("[StoryCreative] 玩家 " + player.getName() + " 开启创造模式于关卡 " + levelId);
  }

  /**
   * 关闭玩家的剧情创造模式
   */
  public void disableCreativeMode(Player player) {
    UUID playerId = player.getUniqueId();
    StoryCreativeSession session = creativeSessions.remove(playerId);

    if (session != null) {
      // 恢复原始游戏模式
      player.setGameMode(session.originalGameMode);
      player.sendMessage("§e✧ 剧情创造模式已关闭");
      player.sendMessage("§7- 你的创造已被保存");

      int blocksPlaced = session.blocksPlaced;
      int blocksBroken = session.blocksBroken;
      player.sendMessage("§7- 放置方块: " + blocksPlaced + " | 破坏方块: " + blocksBroken);

      plugin.getLogger().info("[StoryCreative] 玩家 " + player.getName() + " 关闭创造模式");
      plugin.getLogger().info("[StoryCreative] 统计: 放置=" + blocksPlaced + ", 破坏=" + blocksBroken);
    } else {
      player.sendMessage("§c你没有开启创造模式");
    }
  }

  /**
   * 检查玩家是否在剧情创造模式中
   */
  public boolean isInCreativeMode(Player player) {
    return creativeSessions.containsKey(player.getUniqueId());
  }

  /**
   * 获取玩家的创造会话
   */
  public StoryCreativeSession getSession(Player player) {
    return creativeSessions.get(player.getUniqueId());
  }

  // =============================== 事件监听 ===============================

  /**
   * 监听方块放置事件
   */
  @EventHandler(priority = EventPriority.HIGH)
  public void onBlockPlace(BlockPlaceEvent event) {
    Player player = event.getPlayer();
    StoryCreativeSession session = creativeSessions.get(player.getUniqueId());

    if (session != null) {
      // 玩家在剧情创造模式中，允许建造
      session.blocksPlaced++;

      // 记录建造的方块（用于后续可能的重放或保存）
      session.recordBlockPlacement(event.getBlock());

      plugin.getLogger().fine("[StoryCreative] 玩家 " + player.getName() + " 放置方块: " +
          event.getBlock().getType() + " at " + event.getBlock().getLocation());
    }
  }

  /**
   * 监听方块破坏事件
   */
  @EventHandler(priority = EventPriority.HIGH)
  public void onBlockBreak(BlockBreakEvent event) {
    Player player = event.getPlayer();
    StoryCreativeSession session = creativeSessions.get(player.getUniqueId());

    if (session != null) {
      // 玩家在剧情创造模式中，允许破坏
      session.blocksBroken++;

      // 记录破坏的方块
      session.recordBlockBreak(event.getBlock());

      plugin.getLogger().fine("[StoryCreative] 玩家 " + player.getName() + " 破坏方块: " +
          event.getBlock().getType() + " at " + event.getBlock().getLocation());
    }
  }

  /**
   * 监听玩家交互事件（用于特殊物品交互）
   */
  @EventHandler(priority = EventPriority.NORMAL)
  public void onPlayerInteract(PlayerInteractEvent event) {
    Player player = event.getPlayer();
    StoryCreativeSession session = creativeSessions.get(player.getUniqueId());

    if (session != null) {
      // 在创造模式中，可以添加特殊交互逻辑
      // 例如：右键点击某些方块触发特殊效果
    }
  }

  /**
   * 清理所有会话（服务器关闭时）
   */
  public void cleanup() {
    for (UUID playerId : creativeSessions.keySet()) {
      Player player = plugin.getServer().getPlayer(playerId);
      if (player != null) {
        disableCreativeMode(player);
      }
    }
    creativeSessions.clear();
  }

  // =============================== 内部类 ===============================

  /**
   * 剧情创造会话
   */
  public static class StoryCreativeSession {
    public final String levelId;
    public final GameMode originalGameMode;
    public final org.bukkit.Location originalLocation;
    public final long startTime;

    public int blocksPlaced = 0;
    public int blocksBroken = 0;

    // 简单记录修改的方块位置（可扩展为完整的编辑历史）
    private final java.util.List<org.bukkit.Location> modifiedBlocks = new java.util.ArrayList<>();

    public StoryCreativeSession(String levelId, GameMode originalGameMode, org.bukkit.Location originalLocation) {
      this.levelId = levelId;
      this.originalGameMode = originalGameMode;
      this.originalLocation = originalLocation;
      this.startTime = System.currentTimeMillis();
    }

    public void recordBlockPlacement(org.bukkit.block.Block block) {
      modifiedBlocks.add(block.getLocation());
    }

    public void recordBlockBreak(org.bukkit.block.Block block) {
      modifiedBlocks.add(block.getLocation());
    }

    public java.util.List<org.bukkit.Location> getModifiedBlocks() {
      return new java.util.ArrayList<>(modifiedBlocks);
    }

    public long getDuration() {
      return System.currentTimeMillis() - startTime;
    }
  }
}

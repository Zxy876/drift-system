package com.driftmc.listeners;

import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.tutorial.TutorialManager;

/**
 * 玩家加入/离开事件监听器
 */
public class PlayerJoinListener implements Listener {

  private final JavaPlugin plugin;
  private final TutorialManager tutorialManager;

  public PlayerJoinListener(JavaPlugin plugin, TutorialManager tutorialManager) {
    this.plugin = plugin;
    this.tutorialManager = tutorialManager;
  }

  @EventHandler
  public void onPlayerJoin(PlayerJoinEvent event) {
    Player player = event.getPlayer();

    // 检查是否是新玩家
    if (tutorialManager.isNewPlayer(player)) {
      plugin.getLogger().info("[教学] 检测到新玩家: " + player.getName());

      // 延迟2秒启动教学，让玩家先加载完成
      plugin.getServer().getScheduler().runTaskLater(plugin, () -> {
        if (player.isOnline()) {
          tutorialManager.startTutorial(player);
        }
      }, 40L); // 40 ticks = 2 seconds
    } else {
      plugin.getLogger().info("[教学] 老玩家加入: " + player.getName());
    }
  }

  @EventHandler
  public void onPlayerQuit(PlayerQuitEvent event) {
    Player player = event.getPlayer();
    tutorialManager.cleanupPlayer(player);
  }
}

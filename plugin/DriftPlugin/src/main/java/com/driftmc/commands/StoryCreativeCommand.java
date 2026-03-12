package com.driftmc.commands;

import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

import com.driftmc.DriftPlugin;
import com.driftmc.story.StoryCreativeManager;
import com.driftmc.story.StoryManager;

/**
 * StoryCreativeCommand - /storycreative 命令
 * 
 * 用法：
 * - /storycreative on - 开启剧情创造模式
 * - /storycreative off - 关闭剧情创造模式
 * - /storycreative - 查看当前状态
 */
public class StoryCreativeCommand implements CommandExecutor {

  private final DriftPlugin plugin;
  private final StoryCreativeManager creativeManager;
  private final StoryManager storyManager;

  public StoryCreativeCommand(DriftPlugin plugin, StoryCreativeManager creativeManager, StoryManager storyManager) {
    this.plugin = plugin;
    this.creativeManager = creativeManager;
    this.storyManager = storyManager;
  }

  @Override
  public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
    if (!(sender instanceof Player player)) {
      sender.sendMessage("§c只有玩家可以使用此命令");
      return true;
    }

    // 无参数 - 查看状态
    if (args.length == 0) {
      showStatus(player);
      return true;
    }

    String action = args[0].toLowerCase();

    switch (action) {
      case "on", "enable", "start" -> enableCreative(player);
      case "off", "disable", "stop" -> disableCreative(player);
      case "status", "info" -> showStatus(player);
      case "help" -> showHelp(player);
      default -> {
        player.sendMessage("§c未知参数: " + action);
        showHelp(player);
      }
    }

    return true;
  }

  /**
   * 开启创造模式
   */
  private void enableCreative(Player player) {
    // 检查玩家是否在剧情中
    String currentLevel = storyManager.getCurrentLevel(player);

    if (currentLevel == null) {
      player.sendMessage("§c你当前不在任何剧情中");
      player.sendMessage("§7提示: 先使用 /level <关卡名> 进入剧情");
      return;
    }

    // 检查是否已经在创造模式中
    if (creativeManager.isInCreativeMode(player)) {
      player.sendMessage("§e你已经在创造模式中了");
      return;
    }

    // 开启创造模式
    creativeManager.enableCreativeMode(player, currentLevel);
  }

  /**
   * 关闭创造模式
   */
  private void disableCreative(Player player) {
    if (!creativeManager.isInCreativeMode(player)) {
      player.sendMessage("§c你没有开启创造模式");
      return;
    }

    creativeManager.disableCreativeMode(player);
  }

  /**
   * 显示状态
   */
  private void showStatus(Player player) {
    player.sendMessage("§6========== 剧情创造模式 ==========");

    boolean inCreative = creativeManager.isInCreativeMode(player);
    String currentLevel = storyManager.getCurrentLevel(player);

    player.sendMessage("§7当前剧情: " + (currentLevel != null ? "§e" + currentLevel : "§c无"));
    player.sendMessage("§7创造模式: " + (inCreative ? "§a开启" : "§c关闭"));

    if (inCreative) {
      var session = creativeManager.getSession(player);
      if (session != null) {
        player.sendMessage("§7关卡: §e" + session.levelId);
        player.sendMessage("§7放置方块: §e" + session.blocksPlaced);
        player.sendMessage("§7破坏方块: §e" + session.blocksBroken);

        long durationSec = session.getDuration() / 1000;
        player.sendMessage("§7持续时间: §e" + durationSec + "秒");
      }
    }

    player.sendMessage("§6==============================");

    if (!inCreative && currentLevel != null) {
      player.sendMessage("§7提示: 使用 §e/storycreative on §7开启创造模式");
    }
  }

  /**
   * 显示帮助
   */
  private void showHelp(Player player) {
    player.sendMessage("§6========== 剧情创造模式 帮助 ==========");
    player.sendMessage("§e/storycreative on§7  - 开启剧情创造模式");
    player.sendMessage("§e/storycreative off§7 - 关闭剧情创造模式");
    player.sendMessage("§e/storycreative§7     - 查看当前状态");
    player.sendMessage("§7");
    player.sendMessage("§7说明：");
    player.sendMessage("§7- 在剧情中可以自由建造");
    player.sendMessage("§7- 你的创造会成为场景的一部分");
    player.sendMessage("§7- 其他玩家进入相同剧情会看到你的创造");
    player.sendMessage("§6====================================");
  }
}

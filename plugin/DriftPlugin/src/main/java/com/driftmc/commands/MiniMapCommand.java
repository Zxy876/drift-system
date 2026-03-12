package com.driftmc.commands;

import java.io.File;

import org.bukkit.Bukkit;
import org.bukkit.ChatColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.minimap.MiniMapDownloader;
import com.driftmc.minimap.MiniMapGUI;

/**
 * /minimap
 * 下载 PNG → 放到 MC 地图
 */
public class MiniMapCommand implements CommandExecutor {

    private final JavaPlugin plugin;
    private final String backendUrl;

    public MiniMapCommand(JavaPlugin plugin, String backendUrl) {
        this.plugin = plugin;
        this.backendUrl = backendUrl;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command cmd, String label, String[] args) {

        if (!(sender instanceof Player player)) {
            sender.sendMessage(ChatColor.RED + "这个命令只能由玩家使用。");
            return true;
        }

        String playerId = player.getName();
        player.sendMessage(ChatColor.AQUA + "绘制「心悦宇宙螺旋小地图」中...");

        // 异步下载 PNG
        Bukkit.getScheduler().runTaskAsynchronously(plugin, () -> {
            try {
                String url = backendUrl + "/minimap/png/" + playerId;
                File png = MiniMapDownloader.download(plugin, url, playerId);

                Bukkit.getScheduler().runTask(plugin, () -> {
                    try {
                        ItemStack map = MiniMapGUI.create(plugin, player, png);
                        player.getInventory().addItem(map);
                        player.sendMessage(ChatColor.LIGHT_PURPLE + "§d一张新的「心悦宇宙 · 螺旋地图」已放入你的背包。");
                    } catch (Exception e) {
                        player.sendMessage(ChatColor.RED + "生成地图失败：" + e.getMessage());
                    }
                });

            } catch (Exception e) {
                Bukkit.getScheduler().runTask(plugin, () ->
                        player.sendMessage(ChatColor.RED + "小地图下载失败：" + e.getMessage())
                );
            }
        });

        return true;
    }
}
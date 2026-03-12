package com.driftmc.minimap;

import java.awt.image.BufferedImage;
import java.io.File;

import javax.imageio.ImageIO;

import org.bukkit.Bukkit;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.inventory.ItemStack;
import org.bukkit.inventory.meta.MapMeta;
import org.bukkit.map.MapView;
import org.bukkit.plugin.java.JavaPlugin;

public class MiniMapGUI {

    public static ItemStack create(JavaPlugin plugin, Player player, File pngFile) {
        try {
            BufferedImage img = ImageIO.read(pngFile);
            if (img == null) {
                player.sendMessage("§c小地图图片解析失败。");
                return new ItemStack(Material.BARRIER);
            }

            // --- 创建地图物品 ---
            ItemStack item = new ItemStack(Material.FILLED_MAP);
            MapMeta meta = (MapMeta) item.getItemMeta();

            // --- 创建 MapView ---
            MapView view = Bukkit.createMap(player.getWorld());

            // 关键设置：确保地图不会被 Minecraft 判定为“未初始化”
            view.setScale(MapView.Scale.NORMAL);
            view.setUnlimitedTracking(false);
            view.setWorld(player.getWorld());
            view.setLocked(true);

            // 清空默认 renderer
            view.getRenderers().clear();

            // 加入 PNG renderer
            view.addRenderer(new PNGMapRenderer(img));

            // 绑定 MapView 给物品
            meta.setMapView(view);
            meta.setDisplayName("§b心悦宇宙 · 小地图");

            item.setItemMeta(meta);

            return item;

        } catch (Exception e) {
            plugin.getLogger().warning("[MiniMapGUI] failed: " + e.getMessage());
            player.sendMessage("§c小地图加载失败：" + e.getMessage());
            return new ItemStack(Material.BARRIER);
        }
    }
}
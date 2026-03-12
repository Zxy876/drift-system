package com.driftmc.minimap;

import java.io.File;
import java.io.InputStream;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;

import org.bukkit.plugin.java.JavaPlugin;

/**
 * 负责从后端下载玩家专属的小地图 PNG 文件
 */
public class MiniMapDownloader {

    /**
     * 下载后端 /minimap/png/{playerId} 到插件 dataFolder 下
     */
    public static File download(JavaPlugin plugin, String url, String playerId) throws Exception {
        // 确保插件数据目录存在
        if (!plugin.getDataFolder().exists()) {
            plugin.getDataFolder().mkdirs();
        }

        File out = new File(plugin.getDataFolder(), "minimap_" + playerId + ".png");

        try (InputStream in = new URL(url).openStream()) {
            Files.copy(in, out.toPath(), StandardCopyOption.REPLACE_EXISTING);
        }

        plugin.getLogger().info("[MiniMapDownloader] downloaded: " + out.getAbsolutePath());
        return out;
    }
}
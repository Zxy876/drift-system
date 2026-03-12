package com.driftmc.minimap;

import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;

import org.bukkit.entity.Player;
import org.bukkit.map.MapCanvas;
import org.bukkit.map.MapRenderer;
import org.bukkit.map.MapView;

/**
 * PNG → Minecraft Map 渲染器
 * 支持透明 / 多玩家 / 高清缩放
 */
public class PNGMapRenderer extends MapRenderer {

    private final BufferedImage source;
    private final BufferedImage scaled;

    public PNGMapRenderer(BufferedImage src) {
        super(true);   // 每个玩家独立渲染
        this.source = src;

        // ★ 高清缩放至 128x128（Minecraft 地图分辨率）
        this.scaled = new BufferedImage(128, 128, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = scaled.createGraphics();
        g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
        g.drawImage(src, 0, 0, 128, 128, null);
        g.dispose();
    }

    @Override
    public void render(MapView view, MapCanvas canvas, Player player) {

        // 重复渲染可保持“动态地图”效果，但你的小地图是静态的→只渲染一次即可
        // 但不同玩家要独立渲染，因此不能使用 rendered=true
        canvas.drawImage(0, 0, scaled);
    }
}
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from typing import Dict, Tuple


class MiniMapRenderer:

    def __init__(self):
        base = Path(__file__).resolve().parents[2]

        # 输出路径
        self.output_dir = base / "static" / "minimap"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.png_path = self.output_dir / "minimap.png"

        # 背景：你生成的书本 PNG
        bg_path = self.output_dir / "background.png"
        if bg_path.exists():
            self.background = Image.open(bg_path).convert("RGBA")
        else:
            self.background = Image.new("RGBA", (1024, 1024), (0, 0, 0, 255))

        # 风格色彩
        self.color_locked = (70, 90, 150, 180)        # 暗蓝（未解锁）
        self.color_unlocked = (50, 255, 200, 255)     # 亮青绿（已解锁）
        self.color_current = (255, 215, 0, 255)       # 金色（当前关卡）
        self.color_player = (255, 100, 100, 255)      # 红色（玩家位置）
        self.color_text_unlocked = (230, 255, 240, 255)  # 亮色文字（已解锁）
        self.color_text_locked = (120, 140, 180, 200)    # 暗色文字（未解锁）

        # 字体
        try:
            self.font = ImageFont.truetype(
                "/Library/Fonts/Arial Unicode.ttf", 24
            )
        except:
            self.font = ImageFont.load_default()

    # ------------------------------------------------------------------
    def render(self, nodes: list, player_pos: Tuple[float, float, float] = None, current_level: str = None):
        canvas = self.background.copy()
        draw = ImageDraw.Draw(canvas)

        # 绘制关卡节点
        for node in nodes:
            pos = node["pos"]
            x, y = pos["x"], pos["y"]
            unlocked = node.get("unlocked", False)
            is_current = node["level"] == current_level

            # 选择颜色
            if is_current:
                color = self.color_current
                text_color = self.color_text_unlocked
                size = 10  # 当前关卡更大
            elif unlocked:
                color = self.color_unlocked
                text_color = self.color_text_unlocked
                size = 7
            else:
                color = self.color_locked
                text_color = self.color_text_locked
                size = 5  # 未解锁更小

            # 外圈光晕（已解锁/当前关卡才有）
            if unlocked or is_current:
                glow_size = size + 8
                draw.ellipse((x - glow_size, y - glow_size, x + glow_size, y + glow_size),
                             fill=(color[0], color[1], color[2], 100))
            
            # 实心球
            draw.ellipse((x - size, y - size, x + size, y + size),
                         fill=color)

            # 文字标签
            draw.text((x + 12, y - 8),
                      node["level"],
                      fill=text_color, font=self.font)

        # 玩家位置（小红点）
        if player_pos:
            px, py, _ = player_pos
            draw.ellipse(
                (px - 6, py - 6, px + 6, py + 6),
                fill=self.color_player,
                outline=(255, 255, 255, 255),
                width=2
            )

        # 保存
        canvas.save(self.png_path)
        return str(self.png_path)
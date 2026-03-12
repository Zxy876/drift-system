#!/usr/bin/env python3
"""
为旗舰剧情关卡添加独特的场景、NPC和音乐配置。
"""
import json
import os
from pathlib import Path

LEVEL_DIR = Path("data/flagship_levels")

# 为每个关卡定义独特的场景配置
LEVEL_THEMES = {
    1: {
        "theme": "赛道",
        "npc": "赛车手桃子",
        "biome": "plains",
        "music": "pigstep",
        "structure": "race_track",
        "color": "red"
    },
    2: {
        "theme": "图书馆",
        "npc": "图书管理员",
        "biome": "forest",
        "music": "cat",
        "structure": "library",
        "color": "blue"
    },
    3: {
        "theme": "山顶",
        "npc": "登山者",
        "biome": "mountain",
        "music": "ward",
        "structure": "summit",
        "color": "white"
    },
    4: {
        "theme": "海边",
        "npc": "渔夫",
        "biome": "beach",
        "music": "wait",
        "structure": "dock",
        "color": "cyan"
    },
    5: {
        "theme": "森林",
        "npc": "护林员",
        "biome": "forest",
        "music": "blocks",
        "structure": "tree_house",
        "color": "green"
    },
    6: {
        "theme": "沙漠",
        "npc": "旅行商人",
        "biome": "desert",
        "music": "far",
        "structure": "oasis",
        "color": "yellow"
    },
    7: {
        "theme": "雪山",
        "npc": "雪人向导",
        "biome": "snowy",
        "music": "mall",
        "structure": "igloo",
        "color": "light_blue"
    },
    8: {
        "theme": "花园",
        "npc": "园丁",
        "biome": "flower_forest",
        "music": "mellohi",
        "structure": "garden",
        "color": "pink"
    },
    9: {
        "theme": "废墟",
        "npc": "考古学家",
        "biome": "badlands",
        "music": "stal",
        "structure": "ruins",
        "color": "orange"
    },
    10: {
        "theme": "湖泊",
        "npc": "诗人",
        "biome": "river",
        "music": "strad",
        "structure": "pavilion",
        "color": "aqua"
    },
    11: {
        "theme": "竹林",
        "npc": "武者",
        "biome": "bamboo_jungle",
        "music": "chirp",
        "structure": "dojo",
        "color": "lime"
    },
    12: {
        "theme": "峡谷",
        "npc": "探险家",
        "biome": "canyon",
        "music": "13",
        "structure": "bridge",
        "color": "gray"
    },
    13: {
        "theme": "洞穴",
        "npc": "矿工",
        "biome": "cave",
        "music": "otherside",
        "structure": "mine",
        "color": "brown"
    },
    14: {
        "theme": "神殿",
        "npc": "祭司",
        "biome": "jungle",
        "music": "pigstep",
        "structure": "temple",
        "color": "purple"
    },
    15: {
        "theme": "城堡",
        "npc": "骑士",
        "biome": "plains",
        "music": "cat",
        "structure": "castle",
        "color": "light_gray"
    },
    16: {
        "theme": "塔楼",
        "npc": "巫师",
        "biome": "dark_forest",
        "music": "ward",
        "structure": "tower",
        "color": "magenta"
    },
    17: {
        "theme": "市集",
        "npc": "商人",
        "biome": "plains",
        "music": "wait",
        "structure": "market",
        "color": "orange"
    },
    18: {
        "theme": "港口",
        "npc": "船长",
        "biome": "beach",
        "music": "blocks",
        "structure": "harbor",
        "color": "blue"
    },
    19: {
        "theme": "悬崖",
        "npc": "隐士",
        "biome": "mountain",
        "music": "far",
        "structure": "cliff_dwelling",
        "color": "red"
    },
    20: {
        "theme": "瀑布",
        "npc": "冒险者",
        "biome": "river",
        "music": "mall",
        "structure": "waterfall",
        "color": "cyan"
    },
    21: {
        "theme": "温泉",
        "npc": "疗养师",
        "biome": "plains",
        "music": "mellohi",
        "structure": "hot_spring",
        "color": "pink"
    },
    22: {
        "theme": "天文台",
        "npc": "天文学家",
        "biome": "mountain",
        "music": "stal",
        "structure": "observatory",
        "color": "purple"
    },
    23: {
        "theme": "灯塔",
        "npc": "守塔人",
        "biome": "beach",
        "music": "strad",
        "structure": "lighthouse",
        "color": "yellow"
    },
    24: {
        "theme": "农田",
        "npc": "农夫",
        "biome": "plains",
        "music": "chirp",
        "structure": "farm",
        "color": "green"
    },
    25: {
        "theme": "工坊",
        "npc": "工匠",
        "biome": "village",
        "music": "13",
        "structure": "workshop",
        "color": "brown"
    },
    26: {
        "theme": "学院",
        "npc": "教授",
        "biome": "plains",
        "music": "otherside",
        "structure": "academy",
        "color": "blue"
    },
    27: {
        "theme": "剧院",
        "npc": "演员",
        "biome": "plains",
        "music": "pigstep",
        "structure": "theater",
        "color": "red"
    },
    28: {
        "theme": "画廊",
        "npc": "画家",
        "biome": "plains",
        "music": "cat",
        "structure": "gallery",
        "color": "white"
    },
    29: {
        "theme": "音乐厅",
        "npc": "音乐家",
        "biome": "plains",
        "music": "ward",
        "structure": "concert_hall",
        "color": "gold"
    },
    30: {
        "theme": "心悦殿堂",
        "npc": "心悦守护者",
        "biome": "end",
        "music": "wait",
        "structure": "grand_hall",
        "color": "light_purple"
    }
}

def enhance_level(level_num):
    """为指定关卡添加场景配置"""
    level_file = LEVEL_DIR / f"level_{level_num:02d}.json"
    
    if not level_file.exists():
        print(f"⚠️  {level_file} 不存在")
        return
    
    with open(level_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    theme = LEVEL_THEMES.get(level_num, LEVEL_THEMES[1])
    
    # 添加world_patch配置
    data["world_patch"] = {
        "mc": {
            "spawn": {
                "type": "villager",
                "name": theme["npc"],
                "offset": {"dx": 3, "dy": 0, "dz": 3}
            },
            "build": {
                "shape": "platform",
                "size": 6,
                "material": "stone_bricks"
            },
            "music": {
                "record": theme["music"]
            },
            "particle": {
                "type": "end_rod",
                "color": theme["color"],
                "count": 10
            },
            "tell": f"✨ 欢迎来到【{theme['theme']}】- {data.get('title', '心悦文集')}"
        },
        "variables": {
            "theme": theme["theme"],
            "biome": theme["biome"],
            "structure": theme["structure"],
            "unlocked": False  # 初始状态未解锁
        }
    }
    
    # 保存
    with open(level_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ level_{level_num:02d}.json - {theme['theme']} ({theme['npc']})")

def main():
    print("🎨 开始增强心悦文集关卡...")
    print(f"📁 目录: {LEVEL_DIR.absolute()}")
    print()
    
    for level_num in range(1, 31):
        enhance_level(level_num)
    
    print()
    print("✅ 所有30个关卡已增强完成！")
    print("每个关卡现在都有：")
    print("  • 独特的主题场景")
    print("  • 专属NPC")
    print("  • 背景音乐")
    print("  • 粒子效果")
    print("  • 建筑结构")

if __name__ == "__main__":
    main()

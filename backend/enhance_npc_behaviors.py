#!/usr/bin/env python3
"""
为心悦文集30个关卡的NPC添加特定行为配置
"""

import json
import os
from pathlib import Path

# NPC行为配置
NPC_BEHAVIORS = {
    "level_01": {
        "npc_name": "赛车手桃子",
        "behaviors": [
            {
                "type": "patrol",
                "path": [{"dx": 0, "dz": 5}, {"dx": 5, "dz": 5}, {"dx": 5, "dz": 0}, {"dx": 0, "dz": 0}],
                "speed": 1.2,
                "description": "在赛道周围巡逻"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§e[桃子]§r 你好！想要挑战一百公里飘移吗？",
                    "§e[桃子]§r 记住，不能驻车！提速就要全力以赴！",
                    "§7提示：尝试说'我想学习飘移技巧'来获得帮助"
                ],
                "description": "右键互动时显示对话"
            },
            {
                "type": "quest",
                "trigger_keywords": ["飘移", "赛车", "技巧"],
                "quest_name": "飘移入门",
                "rewards": ["speed_boost", "experience"],
                "description": "玩家提到关键词时触发任务"
            }
        ],
        "ai_hints": "桃子是热血的赛车手，对速度和技巧充满热情。他会鼓励玩家勇敢尝试，不要害怕失败。"
    },
    "level_02": {
        "npc_name": "图书管理员",
        "behaviors": [
            {
                "type": "stand",
                "location": {"dx": 0, "dy": 0, "dz": 0},
                "look_at": "nearest_player",
                "description": "站在书架旁，看向最近的玩家"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§b[管理员]§r 欢迎来到知识的殿堂。",
                    "§b[管理员]§r 这里的每本书都蕴含着智慧...",
                    "§7提示：说'我想找关于X的书'来获取知识"
                ],
                "description": "提供知识查询服务"
            },
            {
                "type": "quest",
                "trigger_keywords": ["书", "知识", "学习"],
                "quest_name": "知识探索",
                "rewards": ["book", "wisdom_points"],
                "description": "帮助玩家查找知识"
            }
        ],
        "ai_hints": "图书管理员博学多识，说话温和有礼。会根据玩家需求推荐合适的知识内容。"
    },
    "level_03": {
        "npc_name": "登山者",
        "behaviors": [
            {
                "type": "climb",
                "target_height": 10,
                "speed": 0.8,
                "description": "缓慢向山顶攀登"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§6[登山者]§r 山顶的风景值得一切付出。",
                    "§6[登山者]§r 每一步都是进步，不要停下脚步。",
                    "§7提示：说'我想攀登高峰'来接受挑战"
                ],
                "description": "分享登山哲学"
            },
            {
                "type": "quest",
                "trigger_keywords": ["攀登", "山峰", "挑战"],
                "quest_name": "攀登之路",
                "rewards": ["climbing_gear", "achievement"],
                "description": "引导玩家体验攀登"
            }
        ],
        "ai_hints": "登山者坚韧不拔，充满毅力。会用登山的比喻来引导玩家克服困难。"
    },
    "level_04": {
        "npc_name": "渔夫",
        "behaviors": [
            {
                "type": "fish",
                "location": "nearest_water",
                "animation": "fishing",
                "description": "在水边垂钓"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§3[渔夫]§r 钓鱼需要耐心，就像人生一样。",
                    "§3[渔夫]§r 有时候，等待比行动更重要。",
                    "§7提示：说'教我钓鱼'来学习技巧"
                ],
                "description": "传授钓鱼与人生智慧"
            },
            {
                "type": "quest",
                "trigger_keywords": ["钓鱼", "耐心", "海边"],
                "quest_name": "垂钓时光",
                "rewards": ["fishing_rod", "patience_buff"],
                "description": "学习耐心的艺术"
            }
        ],
        "ai_hints": "渔夫性格平和，富有哲理。喜欢用钓鱼的道理来启发玩家。"
    },
    "level_05": {
        "npc_name": "护林员",
        "behaviors": [
            {
                "type": "patrol",
                "path": [{"dx": -5, "dz": -5}, {"dx": 5, "dz": -5}, {"dx": 5, "dz": 5}, {"dx": -5, "dz": 5}],
                "speed": 0.9,
                "description": "巡视森林保护环境"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§2[护林员]§r 森林是生命的源泉，我们要好好保护它。",
                    "§2[护林员]§r 每一棵树都有故事，你愿意倾听吗？",
                    "§7提示：说'我想了解森林'来探索自然"
                ],
                "description": "讲述森林故事"
            },
            {
                "type": "quest",
                "trigger_keywords": ["森林", "保护", "自然"],
                "quest_name": "森林守护者",
                "rewards": ["nature_blessing", "seeds"],
                "description": "保护森林生态"
            }
        ],
        "ai_hints": "护林员热爱自然，责任心强。会教育玩家环保意识和对自然的尊重。"
    },
    "level_06": {
        "npc_name": "商人",
        "behaviors": [
            {
                "type": "stand",
                "location": {"dx": 0, "dy": 0, "dz": 0},
                "animation": "trading",
                "description": "站在摊位前等待顾客"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "trade",
                "messages": [
                    "§e[商人]§r 欢迎光临！我这里有最好的商品！",
                    "§e[商人]§r 需要什么尽管说，价格公道！",
                    "§7提示：说'我想交易X'来进行买卖"
                ],
                "description": "提供交易服务"
            },
            {
                "type": "quest",
                "trigger_keywords": ["交易", "商品", "买卖"],
                "quest_name": "沙漠商路",
                "rewards": ["coins", "rare_items"],
                "description": "参与商业活动"
            }
        ],
        "ai_hints": "商人精明能干，善于交际。会根据玩家需求推荐合适商品，偶尔讨价还价。"
    },
    "level_07": {
        "npc_name": "雪人",
        "behaviors": [
            {
                "type": "stand",
                "location": {"dx": 0, "dy": 0, "dz": 0},
                "particle": "snowflake",
                "description": "静静站立，周围飘雪花"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§f[雪人]§r ❄ 寒冷中也有温暖的故事...",
                    "§f[雪人]§r ❄ 我在这里已经很久了，看过无数风雪。",
                    "§7提示：说'讲讲雪山的故事'来倾听往事"
                ],
                "description": "分享雪山传说"
            },
            {
                "type": "quest",
                "trigger_keywords": ["雪", "寒冷", "故事"],
                "quest_name": "冰雪传说",
                "rewards": ["frost_resistance", "snowball"],
                "description": "探索雪山秘密"
            }
        ],
        "ai_hints": "雪人古老神秘，说话缓慢深沉。知晓许多关于雪山的传说和秘密。"
    },
    "level_08": {
        "npc_name": "矿工",
        "behaviors": [
            {
                "type": "mine",
                "animation": "mining",
                "sound": "stone_break",
                "description": "挖掘矿石"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§7[矿工]§r ⛏ 地下有无尽的宝藏！",
                    "§7[矿工]§r ⛏ 但要小心，洞穴里也有危险...",
                    "§7提示：说'教我挖矿'来学习采矿技巧"
                ],
                "description": "传授采矿经验"
            },
            {
                "type": "quest",
                "trigger_keywords": ["挖矿", "宝藏", "洞穴"],
                "quest_name": "矿工学徒",
                "rewards": ["pickaxe", "ore"],
                "description": "学习采矿技能"
            }
        ],
        "ai_hints": "矿工勤劳朴实，经验丰富。会分享采矿技巧和洞穴探险故事。"
    },
    "level_09": {
        "npc_name": "园丁",
        "behaviors": [
            {
                "type": "garden",
                "animation": "watering",
                "particle": "water_splash",
                "description": "浇灌花园"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§d[园丁]§r 🌸 每一朵花都需要细心呵护。",
                    "§d[园丁]§r 🌸 生命的美丽需要耐心培育。",
                    "§7提示：说'我想种花'来学习园艺"
                ],
                "description": "教授园艺知识"
            },
            {
                "type": "quest",
                "trigger_keywords": ["花", "园艺", "种植"],
                "quest_name": "花园艺术",
                "rewards": ["seeds", "flowers"],
                "description": "学习园艺技能"
            }
        ],
        "ai_hints": "园丁温柔细致，热爱生命。会用植物生长比喻人生成长。"
    },
    "level_10": {
        "npc_name": "诗人",
        "behaviors": [
            {
                "type": "wander",
                "radius": 8,
                "speed": 0.7,
                "description": "在湖边漫步思考"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§b[诗人]§r 📖 湖水如镜，映照内心...",
                    "§b[诗人]§r 📖 让我为你吟诵一首诗吧。",
                    "§7提示：说'我想听诗'来欣赏诗歌"
                ],
                "description": "吟诵诗歌"
            },
            {
                "type": "quest",
                "trigger_keywords": ["诗", "文学", "灵感"],
                "quest_name": "诗意人生",
                "rewards": ["poem_book", "inspiration"],
                "description": "体验诗歌艺术"
            }
        ],
        "ai_hints": "诗人浪漫感性，富有文采。会即兴创作诗歌，用诗意的语言交流。"
    },
    # 继续配置level_11到level_30...
    "level_11": {
        "npc_name": "村长",
        "behaviors": [
            {
                "type": "stand",
                "location": {"dx": 0, "dy": 0, "dz": 0},
                "look_at": "nearest_player",
                "description": "在村中心等待村民"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§6[村长]§r 欢迎来到我们的村庄！",
                    "§6[村长]§r 这里的每个人都很友善。",
                    "§7提示：说'村里有什么'来了解村庄"
                ],
                "description": "介绍村庄情况"
            }
        ],
        "ai_hints": "村长慈祥和蔼，关心村民。会介绍村庄历史和居民故事。"
    },
    "level_30": {
        "npc_name": "心悦守护者",
        "behaviors": [
            {
                "type": "float",
                "height": 2.0,
                "particle": "soul_fire_flame",
                "description": "悬浮在空中，散发神圣光芒"
            },
            {
                "type": "interact",
                "trigger": "right_click",
                "action": "dialogue",
                "messages": [
                    "§e✨[心悦守护者]§r 你终于到达了终点。",
                    "§e✨[心悦守护者]§r 但这不是结束，而是新的开始...",
                    "§7提示：说'我准备好了'来完成最终挑战"
                ],
                "description": "给予最终考验"
            },
            {
                "type": "quest",
                "trigger_keywords": ["完成", "结束", "挑战"],
                "quest_name": "心悦之旅终章",
                "rewards": ["legendary_item", "completion"],
                "description": "完成所有试炼"
            }
        ],
        "ai_hints": "心悦守护者神圣庄严，智慧无边。会总结玩家的整个旅程，给予最终指引。"
    }
}

# 为缺少的关卡添加默认配置
for i in range(12, 30):
    if f"level_{i:02d}" not in NPC_BEHAVIORS:
        NPC_BEHAVIORS[f"level_{i:02d}"] = {
            "npc_name": f"关卡{i}守护者",
            "behaviors": [
                {
                    "type": "stand",
                    "location": {"dx": 0, "dy": 0, "dz": 0},
                    "description": "等待玩家到来"
                },
                {
                    "type": "interact",
                    "trigger": "right_click",
                    "action": "dialogue",
                    "messages": [
                        f"§a[守护者]§r 欢迎来到第{i}关。",
                        "§7提示：尝试与我对话了解更多"
                    ],
                    "description": "提供关卡指引"
                }
            ],
            "ai_hints": f"第{i}关的守护者，会根据关卡主题提供帮助和指引。"
        }


def enhance_npc_behaviors():
    """为所有关卡的world_patch添加NPC行为配置"""
    data_dir = Path(__file__).parent / "data" / "flagship_levels"
    
    if not data_dir.exists():
        print(f"❌ 目录不存在: {data_dir}")
        return
    
    success_count = 0
    
    for level_id, npc_config in NPC_BEHAVIORS.items():
        json_path = data_dir / f"{level_id}.json"
        
        if not json_path.exists():
            print(f"⚠️  文件不存在: {json_path}")
            continue
        
        try:
            # 读取现有配置
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 确保world_patch存在
            if "world_patch" not in data:
                data["world_patch"] = {"mc": {}, "variables": {}}
            
            # 添加NPC行为配置
            if "mc" not in data["world_patch"]:
                data["world_patch"]["mc"] = {}
            
            # 更新spawn配置，添加behaviors
            if "spawn" in data["world_patch"]["mc"]:
                data["world_patch"]["mc"]["spawn"]["behaviors"] = npc_config["behaviors"]
                data["world_patch"]["mc"]["spawn"]["ai_hints"] = npc_config["ai_hints"]
            else:
                # 如果没有spawn配置，创建一个
                data["world_patch"]["mc"]["spawn"] = {
                    "type": "villager",
                    "name": npc_config["npc_name"],
                    "offset": {"dx": 3, "dy": 0, "dz": 3},
                    "behaviors": npc_config["behaviors"],
                    "ai_hints": npc_config["ai_hints"]
                }
            
            # 写回文件
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ {level_id}.json - {npc_config['npc_name']} (添加了{len(npc_config['behaviors'])}个行为)")
            success_count += 1
            
        except Exception as e:
            print(f"❌ 处理 {level_id}.json 时出错: {e}")
    
    print(f"\n✅ 完成！成功增强了 {success_count} 个关卡的NPC行为配置")


if __name__ == "__main__":
    enhance_npc_behaviors()

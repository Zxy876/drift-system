# backend/app/core/tutorial/tutorial_system.py
"""
交互式新手指引系统
通过步骤化的教学引导玩家了解所有功能
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum


class TutorialStep(Enum):
    """教学步骤枚举"""
    WELCOME = "welcome"
    DIALOGUE = "dialogue"
    CREATE_STORY = "create_story"
    CONTINUE_STORY = "continue_story"
    JUMP_LEVEL = "jump_level"
    NPC_INTERACT = "npc_interact"
    VIEW_MAP = "view_map"
    COMPLETE = "complete"


@dataclass
class TutorialProgress:
    """玩家的教学进度"""
    player_id: str
    current_step: TutorialStep
    completed_steps: List[TutorialStep]
    hints_shown: int
    is_completed: bool


class TutorialSystem:
    """新手教学系统"""
    
    def __init__(self):
        self.player_progress: Dict[str, TutorialProgress] = {}
        self.step_configs = self._init_step_configs()
    
    def _init_step_configs(self) -> Dict[TutorialStep, Dict[str, Any]]:
        """初始化每个教学步骤的配置"""
        return {
            TutorialStep.WELCOME: {
                "title": "§e✨ 欢迎来到心悦文集",
                "description": "这是一个由AI驱动的互动故事世界",
                "instruction": "§7请在聊天框输入：§f'你好'§7 或 §f'我准备好了'",
                "trigger_keywords": ["你好", "hi", "hello", "准备", "ready"],
                "success_message": "§a✓ 很好！你已经学会了基本对话",
                "reward": {
                    "tell": "§b💡 提示：你可以随时用自然语言与系统对话",
                    "effect": None
                },
                "next_step": TutorialStep.DIALOGUE
            },
            TutorialStep.DIALOGUE: {
                "title": "§b📖 第一课：自由对话",
                "description": "在这个世界里，你的每一句话都有意义",
                "instruction": "§7试着问我：§f'这里是什么地方？'§7 或随便说点什么",
                "trigger_keywords": ["什么", "哪里", "地方", "是谁", "怎么", "为什么"],
                "success_message": "§a✓ 太棒了！AI理解了你的问题",
                "reward": {
                    "tell": "§b💡 系统会用AI理解你的意图并作出回应",
                    "give_xp": 50
                },
                "next_step": TutorialStep.CREATE_STORY
            },
            TutorialStep.CREATE_STORY: {
                "title": "§d🎭 第二课：创造剧情",
                "description": "你可以让AI为你生成独特的故事",
                "instruction": "§7输入：§f'写一个剧情'§7 或 §f'创造故事'",
                "trigger_keywords": ["写", "剧情", "故事", "创造", "生成"],
                "success_message": "§a✓ 精彩！你创造了自己的故事",
                "reward": {
                    "tell": "§b💡 每次生成的剧情都是独一无二的",
                    "give_xp": 100
                },
                "next_step": TutorialStep.CONTINUE_STORY
            },
            TutorialStep.CONTINUE_STORY: {
                "title": "§6⏭ 第三课：推进剧情",
                "description": "你可以继续当前的故事或做出选择",
                "instruction": "§7输入：§f'继续'§7 或 §f'下一步'",
                "trigger_keywords": ["继续", "下一步", "next", "然后"],
                "success_message": "§a✓ 完美！故事在你的选择中延续",
                "reward": {
                    "tell": "§b💡 你的选择会影响故事的发展方向",
                    "effect": {
                        "type": "REGENERATION",
                        "duration": 200,
                        "amplifier": 0
                    }
                },
                "next_step": TutorialStep.JUMP_LEVEL
            },
            TutorialStep.JUMP_LEVEL: {
                "title": "§c🚀 第四课：关卡跳转",
                "description": "心悦文集有30个关卡等待你探索",
                "instruction": "§7输入：§f'跳到第一关'§7 来开始正式冒险",
                "trigger_keywords": ["跳", "第", "关", "前往", "go", "level"],
                "success_message": "§a✓ 厉害！你学会了快速导航",
                "reward": {
                    "tell": "§b💡 每个关卡都有独特的场景、NPC和音乐",
                    "give_xp": 150
                },
                "next_step": TutorialStep.NPC_INTERACT
            },
            TutorialStep.NPC_INTERACT: {
                "title": "§e👥 第五课：NPC互动",
                "description": "每个关卡都有独特的NPC角色",
                "instruction": "§7试着对NPC说：§f'你好'§7 或右键点击NPC",
                "trigger_keywords": ["你好", "hi", "教", "帮助", "任务"],
                "success_message": "§a✓ 太好了！你与NPC建立了联系",
                "reward": {
                    "tell": "§b💡 用关键词可以触发NPC的特殊任务",
                    "effect": {
                        "type": "SPEED",
                        "duration": 600,
                        "amplifier": 0
                    }
                },
                "next_step": TutorialStep.VIEW_MAP
            },
            TutorialStep.VIEW_MAP: {
                "title": "§a🗺 第六课：小地图",
                "description": "查看你的冒险进度和已解锁的关卡",
                "instruction": "§7输入：§f'给我小地图'§7 或 §f'查看地图'",
                "trigger_keywords": ["地图", "map", "小地图", "进度"],
                "success_message": "§a✓ 完美！你已经掌握了所有基础功能",
                "reward": {
                    "tell": "§e✨ 恭喜完成新手教学！你现在可以自由探索了",
                    "give_xp": 500,
                    "effect": {
                        "type": "GLOWING",
                        "duration": 600,
                        "amplifier": 0
                    }
                },
                "next_step": TutorialStep.COMPLETE
            },
            TutorialStep.COMPLETE: {
                "title": "§6🎉 教学完成",
                "description": "你已经掌握了心悦文集的所有基础功能",
                "instruction": "§a现在，开始你的冒险吧！",
                "trigger_keywords": [],
                "success_message": "§6✨ 祝你在心悦文集中有美好的旅程！",
                "reward": {
                    "tell": "§d💝 新手礼包已发放！",
                    "give_items": [
                        {"type": "DIAMOND", "amount": 5},
                        {"type": "GOLDEN_APPLE", "amount": 3},
                        {"type": "BOOK", "amount": 1}
                    ]
                },
                "next_step": None
            }
        }
    
    def start_tutorial(self, player_id: str) -> Dict[str, Any]:
        """开始新手教学"""
        self.player_progress[player_id] = TutorialProgress(
            player_id=player_id,
            current_step=TutorialStep.WELCOME,
            completed_steps=[],
            hints_shown=0,
            is_completed=False
        )
        
        return self._get_step_info(TutorialStep.WELCOME)
    
    def check_progress(self, player_id: str, message: str) -> Optional[Dict[str, Any]]:
        """
        检查玩家输入是否完成当前教学步骤
        返回None表示未触发，返回dict表示步骤完成
        """
        if player_id not in self.player_progress:
            return None
        
        progress = self.player_progress[player_id]
        if progress.is_completed:
            return None
        
        current_step = progress.current_step
        config = self.step_configs[current_step]
        
        # 检查是否包含触发关键词
        message_lower = message.lower()
        keywords = config["trigger_keywords"]
        
        if any(kw in message_lower or kw in message for kw in keywords):
            # 步骤完成
            return self._complete_step(player_id, current_step)
        
        return None
    
    def _complete_step(self, player_id: str, step: TutorialStep) -> Dict[str, Any]:
        """完成一个教学步骤"""
        progress = self.player_progress[player_id]
        config = self.step_configs[step]
        
        # 标记步骤完成
        if step not in progress.completed_steps:
            progress.completed_steps.append(step)
        
        # 移动到下一步
        next_step = config["next_step"]
        if next_step:
            progress.current_step = next_step
        else:
            progress.is_completed = True
        
        # 构建响应
        response = {
            "status": "step_completed",
            "step": step.value,
            "success_message": config["success_message"],
            "reward": config["reward"],
            "mc": self._build_mc_commands(config["reward"])
        }
        
        # 如果有下一步，添加下一步信息
        if next_step:
            next_config = self.step_configs[next_step]
            response["next_step"] = {
                "title": next_config["title"],
                "description": next_config["description"],
                "instruction": next_config["instruction"]
            }
        
        return response
    
    def _build_mc_commands(self, reward: Dict[str, Any]) -> List[Dict[str, Any]]:
        """构建MC指令"""
        commands = []
        
        if reward.get("tell"):
            commands.append({"tell": reward["tell"]})
        
        if reward.get("give_xp"):
            commands.append({"give_xp": reward["give_xp"]})
        
        if reward.get("effect"):
            commands.append({"effect": reward["effect"]})
        
        if reward.get("give_items"):
            for item in reward["give_items"]:
                commands.append({"give_item": item})
        
        return commands
    
    def _get_step_info(self, step: TutorialStep) -> Dict[str, Any]:
        """获取步骤信息"""
        config = self.step_configs[step]
        return {
            "title": config["title"],
            "description": config["description"],
            "instruction": config["instruction"]
        }
    
    def get_current_step(self, player_id: str) -> Optional[Dict[str, Any]]:
        """获取玩家当前的教学步骤"""
        if player_id not in self.player_progress:
            return None
        
        progress = self.player_progress[player_id]
        if progress.is_completed:
            return {"status": "completed"}
        
        return self._get_step_info(progress.current_step)
    
    def give_hint(self, player_id: str) -> Optional[str]:
        """给玩家当前步骤的提示"""
        if player_id not in self.player_progress:
            return None
        
        progress = self.player_progress[player_id]
        if progress.is_completed:
            return "§a你已经完成了所有教学！"
        
        config = self.step_configs[progress.current_step]
        progress.hints_shown += 1
        
        return f"{config['title']}\n{config['instruction']}"
    
    def skip_tutorial(self, player_id: str) -> Dict[str, Any]:
        """跳过教学"""
        if player_id in self.player_progress:
            self.player_progress[player_id].is_completed = True
        
        return {
            "status": "skipped",
            "message": "§7已跳过新手教学，祝你冒险愉快！",
            "mc": [{"tell": "§7已跳过新手教学，祝你冒险愉快！"}]
        }


# 全局实例
tutorial_system = TutorialSystem()

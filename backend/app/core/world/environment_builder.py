# backend/app/core/world/environment_builder.py
"""
动态环境构建器 - 根据剧情类型生成真实的、可交互的游戏环境
支持：赛车漂移赛道、考场环境、隧道场景等
"""
from typing import Dict, Any, List, Optional
import math


class EnvironmentBuilder:
    """环境构建器 - 生成具体的MC世界结构"""
    
    def __init__(self):
        self.templates = {
            "drift_track": self._build_drift_track,
            "exam_room": self._build_exam_room,
            "tunnel": self._build_tunnel,
            "void_platform": self._build_void_platform,
            "heart_space": self._build_heart_space,
        }
    
    def build_environment(self, env_type: str, level_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        构建指定类型的环境
        
        Args:
            env_type: 环境类型（drift_track, exam_room, tunnel等）
            level_id: 关卡ID
            params: 额外参数
            
        Returns:
            包含build指令的字典
        """
        params = params or {}
        builder_func = self.templates.get(env_type, self._build_void_platform)
        return builder_func(level_id, params)
    
    def _build_drift_track(self, level_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建赛车漂移赛道
        - 椭圆形赛道
        - 起点/终点标记
        - 弯道区域
        - 赛车实体（可驾驶的矿车）
        """
        track_radius = params.get("radius", 30)
        track_width = params.get("width", 5)
        
        # 赛道中心坐标
        center_x = params.get("center_x", 0)
        center_y = params.get("center_y", 70)
        center_z = params.get("center_z", 0)
        
        return {
            "mc": {
                # 主赛道（椭圆形）
                "build_multi": [
                    {
                        "shape": "race_track",
                        "material": "GRAY_CONCRETE",
                        "center": {"x": center_x, "y": center_y, "z": center_z},
                        "radius_x": track_radius,
                        "radius_z": track_radius * 1.5,  # 椭圆形
                        "width": track_width,
                        "height": 1,
                    },
                    # 起点线（红色）
                    {
                        "shape": "line",
                        "material": "RED_CONCRETE",
                        "start": {"x": center_x - 2, "y": center_y, "z": center_z - track_radius * 1.5},
                        "end": {"x": center_x + 2, "y": center_y, "z": center_z - track_radius * 1.5},
                    },
                    # 终点线（绿色）
                    {
                        "shape": "line",
                        "material": "LIME_CONCRETE",
                        "start": {"x": center_x - 2, "y": center_y, "z": center_z - track_radius * 1.5 + 1},
                        "end": {"x": center_x + 2, "y": center_y, "z": center_z - track_radius * 1.5 + 1},
                    },
                    # 赛道围栏
                    {
                        "shape": "fence_ring",
                        "material": "OAK_FENCE",
                        "center": {"x": center_x, "y": center_y + 1, "z": center_z},
                        "radius_x": track_radius + track_width + 1,
                        "radius_z": track_radius * 1.5 + track_width + 1,
                    },
                ],
                # 生成赛车（可驾驶的矿车 + 展示用实体）
                "spawn_multi": [
                    {
                        "type": "MINECART",
                        "name": "§e赛车·漂移号",
                        "position": {"x": center_x, "y": center_y + 1, "z": center_z - track_radius * 1.5 - 2},
                        "custom_model": True,
                        "rideable": True,
                    },
                    {
                        "type": "ARMOR_STAND",
                        "name": "§6桃子的赛车",
                        "position": {"x": center_x + 5, "y": center_y + 1, "z": center_z - track_radius * 1.5 - 2},
                        "equipment": {
                            "head": "GOLDEN_HELMET",
                            "chest": "IRON_CHESTPLATE",
                        },
                        "pose": "sitting",
                    },
                ],
                "particle": {
                    "type": "SMOKE_NORMAL",
                    "positions": [
                        {"x": center_x, "y": center_y + 0.5, "z": center_z - track_radius * 1.5 - 2},
                    ],
                    "count": 20,
                    "spread": {"x": 0.5, "y": 0.2, "z": 0.5},
                },
                "title": {
                    "main": "§e⚡ 赛车漂移赛道 ⚡",
                    "sub": "§7右键点击矿车开始驾驶",
                },
                "tell": [
                    "§e【赛道系统】赛道已加载完成",
                    "§7- 右键点击矿车开始驾驶",
                    "§7- 使用 WASD 控制方向",
                    "§7- 在弯道处释放方向键进行漂移",
                ],
            }
        }
    
    def _build_exam_room(self, level_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建考场环境
        - 白色房间
        - 书桌和椅子
        - 试卷展示板
        - 时钟装饰
        """
        room_size = params.get("size", 20)
        desk_positions = params.get("desks", 5)
        
        center_x = params.get("center_x", 0)
        center_y = params.get("center_y", 80)
        center_z = params.get("center_z", 0)
        
        return {
            "mc": {
                "build_multi": [
                    # 房间地板
                    {
                        "shape": "platform",
                        "material": "WHITE_CONCRETE",
                        "center": {"x": center_x, "y": center_y, "z": center_z},
                        "size": room_size,
                    },
                    # 房间墙壁
                    {
                        "shape": "hollow_cube",
                        "material": "QUARTZ_BLOCK",
                        "center": {"x": center_x, "y": center_y, "z": center_z},
                        "size": room_size,
                        "height": 6,
                    },
                    # 天花板灯光
                    {
                        "shape": "grid",
                        "material": "SEA_LANTERN",
                        "center": {"x": center_x, "y": center_y + 5, "z": center_z},
                        "size": room_size - 2,
                        "spacing": 4,
                    },
                ],
                # 生成书桌、椅子、试卷
                "spawn_multi": self._generate_exam_desks(
                    center_x, center_y, center_z, desk_positions
                ),
                "particle": {
                    "type": "END_ROD",
                    "positions": [
                        {"x": center_x, "y": center_y + 4, "z": center_z},
                    ],
                    "count": 30,
                    "radius": 3,
                },
                "title": {
                    "main": "§f📝 考试空间",
                    "sub": "§7思考的领域，答案在脑海中",
                },
                "tell": [
                    "§f【考场系统】考试环境已准备就绪",
                    "§7- 靠近书桌查看题目",
                    "§7- 思考后输入答案",
                ],
            }
        }
    
    def _build_tunnel(self, level_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建隧道场景
        - 长隧道结构
        - 昏暗灯光
        - 回音效果
        """
        length = params.get("length", 50)
        width = params.get("width", 5)
        height = params.get("height", 5)
        
        start_x = params.get("start_x", 0)
        start_y = params.get("start_y", 60)
        start_z = params.get("start_z", 0)
        
        return {
            "mc": {
                "build_multi": [
                    # 隧道主体
                    {
                        "shape": "tunnel",
                        "material": "STONE_BRICKS",
                        "start": {"x": start_x, "y": start_y, "z": start_z},
                        "direction": "north",
                        "length": length,
                        "width": width,
                        "height": height,
                    },
                    # 隧道灯光（每隔5格一盏）
                    {
                        "shape": "light_line",
                        "material": "TORCH",
                        "start": {"x": start_x, "y": start_y + height - 1, "z": start_z},
                        "direction": "north",
                        "length": length,
                        "spacing": 5,
                    },
                ],
                "effect": {
                    "type": "DARKNESS",
                    "seconds": 10,
                    "amplifier": 1,
                },
                "sound": {
                    "type": "AMBIENT_CAVE",
                    "volume": 0.5,
                    "pitch": 0.8,
                },
                "particle": {
                    "type": "SMOKE_NORMAL",
                    "count": 50,
                    "radius": 2,
                },
                "title": {
                    "main": "§8⚫ 隧道回溯",
                    "sub": "§7在黑暗中寻找光明",
                },
            }
        }
    
    def _build_void_platform(self, level_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建虚空平台（默认场景）
        - 浮空平台
        - 星空背景
        - 柔和灯光
        """
        size = params.get("size", 12)
        center_x = params.get("center_x", 0)
        center_y = params.get("center_y", 100)
        center_z = params.get("center_z", 0)
        
        return {
            "mc": {
                "build": {
                    "shape": "platform",
                    "material": "SMOOTH_QUARTZ",
                    "center": {"x": center_x, "y": center_y, "z": center_z},
                    "size": size,
                },
                "particle": {
                    "type": "END_ROD",
                    "count": 50,
                    "radius": size / 2,
                },
                "title": {
                    "main": "§d✨ 虚空之境",
                    "sub": "§7思绪在这里自由漂浮",
                },
            }
        }
    
    def _build_heart_space(self, level_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        构建心形空间（特殊场景）
        - 心形平台
        - 粉色主题
        - 温暖氛围
        """
        size = params.get("size", 10)
        center_x = params.get("center_x", 0)
        center_y = params.get("center_y", 90)
        center_z = params.get("center_z", 0)
        
        return {
            "mc": {
                "build": {
                    "shape": "heart_pad",
                    "material": "PINK_CONCRETE",
                    "center": {"x": center_x, "y": center_y, "z": center_z},
                    "size": size,
                },
                "particle": {
                    "type": "HEART",
                    "count": 100,
                    "radius": size / 2,
                },
                "title": {
                    "main": "§d♥ 心悦空间",
                    "sub": "§7温暖包裹着这里的一切",
                },
            }
        }
    
    def _generate_exam_desks(self, center_x: float, center_y: float, center_z: float, 
                           count: int) -> List[Dict[str, Any]]:
        """生成考场的书桌和椅子"""
        spawns = []
        rows = int(math.sqrt(count))
        cols = (count + rows - 1) // rows
        
        spacing = 4
        
        for i in range(count):
            row = i // cols
            col = i % cols
            
            x = center_x - (cols * spacing) / 2 + col * spacing
            z = center_z - (rows * spacing) / 2 + row * spacing
            
            # 书桌（用栅栏和台阶表示）
            spawns.append({
                "type": "ARMOR_STAND",
                "name": f"§7书桌 {i+1}",
                "position": {"x": x, "y": center_y + 1, "z": z},
                "invisible": True,
                "small": True,
                "marker": True,
            })
        
        return spawns


# 全局实例
environment_builder = EnvironmentBuilder()

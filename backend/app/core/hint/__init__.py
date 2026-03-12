"""
Hint 模块
负责系统的推理引擎，实现：
- 根据用户输入给出 summary / reasoning / action
- 与树状态 (TreeEngine) 协同
- 与世界状态 (WorldEngine) 协同
"""

from .engine import HintEngine

__all__ = ["HintEngine"]
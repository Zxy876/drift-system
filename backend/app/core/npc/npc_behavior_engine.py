# backend/app/core/npc/npc_behavior_engine.py
"""
NPC行为引擎：处理NPC的AI驱动行为
"""
from typing import Dict, Any, Iterable, List, Optional, Set
from dataclasses import dataclass

from app.core.story.level_schema import RuleListener


@dataclass
class NPCBehavior:
    """NPC行为定义"""
    type: str  # patrol, stand, interact, quest, wander, etc.
    config: Dict[str, Any]
    description: str


class NPCBehaviorEngine:
    """NPC行为引擎"""
    
    def __init__(self):
        self.active_npcs: Dict[str, Dict[str, Any]] = {}  # level_id -> npc_data
        self.rule_bindings: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.active_rule_refs: Dict[str, Set[str]] = {}
    
    def register_npc(self, level_id: str, npc_data: Dict[str, Any]):
        """注册NPC及其行为"""
        self.active_npcs[level_id] = npc_data
        self.rule_bindings.setdefault(level_id, {})
        self.active_rule_refs.setdefault(level_id, set())

    def register_rule_binding(self, level_id: str, listener: RuleListener) -> None:
        """记录 rulegraph 监听配置以便触发 NPC 行为。"""

        if not listener:
            return

        bindings = self.rule_bindings.setdefault(level_id, {})
        self.active_rule_refs.setdefault(level_id, set())

        meta = dict(getattr(listener, "metadata", {}) or {})
        refs: Set[str] = set()
        for candidate in listener.targets or []:
            if candidate:
                refs.add(str(candidate).lower())
        for key in ("id", "rule_ref", "ref"):
            value = meta.get(key)
            if value:
                refs.add(str(value).lower())
        if listener.quest_event:
            refs.add(str(listener.quest_event).lower())
        if listener.type:
            refs.add(str(listener.type).lower())

        if not refs:
            refs.add(f"listener_{len(bindings)}")

        payload = {
            "metadata": meta,
            "type": listener.type,
            "quest_event": listener.quest_event,
        }

        for ref in refs:
            bindings[ref] = payload

    def activate_rule_refs(self, level_id: str, refs: Iterable[str]) -> None:
        """标记特定 rule_ref 已激活，允许对应 NPC 行为生效。"""

        if not refs:
            return

        active = self.active_rule_refs.setdefault(level_id, set())
        for ref in refs:
            if ref:
                active.add(str(ref).lower())

    def apply_rule_trigger(
        self,
        level_id: str,
        event: Dict[str, Any],
        active_refs: Optional[Iterable[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """根据 rule 事件更新 NPC 状态并返回补充 world_patch/nodes。"""

        bindings = self.rule_bindings.get(level_id)
        if not bindings:
            return None

        candidates: Set[str] = set()
        event_type = event.get("event_type")
        if event_type:
            candidates.add(str(event_type).lower())
        quest_event = event.get("quest_event") or event.get("meta", {}).get("quest_event")
        if quest_event:
            candidates.add(str(quest_event).lower())
        target = event.get("target")
        if target and event_type:
            candidates.add(f"{event_type}:{target}".lower())

        active = set(str(ref).lower() for ref in (active_refs or []))
        active |= self.active_rule_refs.get(level_id, set())
        candidates |= active

        matched = [bindings[ref] for ref in candidates if ref in bindings]
        if not matched:
            return None

        nodes: List[Dict[str, Any]] = []
        world_patch: Dict[str, Any] = {}
        commands: List[str] = []
        applied_behaviors: List[Dict[str, Any]] = []

        for binding in matched:
            meta = dict(binding.get("metadata") or {})

            dialogue = meta.get("dialogue") or meta.get("npc_dialogue")
            if dialogue:
                node = self._build_dialogue_node(dialogue, meta)
                if node:
                    nodes.append(node)

            patch = meta.get("world_patch")
            if isinstance(patch, dict):
                world_patch = self._merge_world_patch(world_patch, patch)

            cmd_list = meta.get("commands")
            if isinstance(cmd_list, list):
                commands.extend(str(cmd) for cmd in cmd_list if cmd)

            behavior_updates = meta.get("update_behaviors")
            if behavior_updates and isinstance(behavior_updates, list):
                npc_data = self.active_npcs.setdefault(level_id, {})
                existing = npc_data.setdefault("behaviors", [])
                for update in behavior_updates:
                    if isinstance(update, dict):
                        existing.append(update)
                        applied_behaviors.append(update)

        result: Dict[str, Any] = {}
        if nodes:
            result["nodes"] = nodes
        if world_patch:
            result["world_patch"] = world_patch
        if commands:
            result["commands"] = commands
        if applied_behaviors:
            result["updated_behaviors"] = applied_behaviors

        return result or None
    
    def get_npc_behaviors(self, level_id: str) -> List[NPCBehavior]:
        """获取NPC的所有行为"""
        if level_id not in self.active_npcs:
            return []
        
        npc_data = self.active_npcs[level_id]
        behaviors = npc_data.get("behaviors", [])
        
        return [
            NPCBehavior(
                type=b.get("type", "stand"),
                config=b,
                description=b.get("description", "")
            )
            for b in behaviors
        ]
    
    def get_npc_ai_hints(self, level_id: str) -> str:
        """获取NPC的AI提示（用于对话生成）"""
        if level_id not in self.active_npcs:
            return ""
        
        return self.active_npcs[level_id].get("ai_hints", "")
    
    def handle_player_interaction(
        self, 
        level_id: str, 
        player_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        处理玩家与NPC的交互
        返回NPC的响应和行为变化
        """
        if level_id not in self.active_npcs:
            return None
        
        npc_data = self.active_npcs[level_id]
        behaviors = npc_data.get("behaviors", [])
        
        # 检查是否触发任务
        for behavior in behaviors:
            if behavior.get("type") == "quest":
                keywords = behavior.get("trigger_keywords", [])
                if any(kw in player_message for kw in keywords):
                    return {
                        "type": "quest_trigger",
                        "quest_name": behavior.get("quest_name"),
                        "rewards": behavior.get("rewards", []),
                        "npc_response": f"看来你对{behavior.get('quest_name')}感兴趣！让我来帮助你。"
                    }
        
        # 检查普通互动
        for behavior in behaviors:
            if behavior.get("type") == "interact":
                keywords = behavior.get("trigger_keywords", [])
                if not keywords or any(kw in player_message for kw in keywords):
                    return {
                        "type": "dialogue",
                        "messages": behavior.get("messages", []),
                        "npc_name": npc_data.get("name", "NPC")
                    }
        
        return None
    
    def generate_mc_commands(
        self, 
        level_id: str, 
        spawn_location: Dict[str, float]
    ) -> List[str]:
        """
        根据NPC行为生成MC命令
        """
        if level_id not in self.active_npcs:
            return []
        
        npc_data = self.active_npcs[level_id]
        behaviors = npc_data.get("behaviors", [])
        commands = []
        
        base_x = spawn_location.get("x", 0)
        base_y = spawn_location.get("y", 100)
        base_z = spawn_location.get("z", 0)
        
        for behavior in behaviors:
            btype = behavior.get("type")
            
            if btype == "patrol":
                # 巡逻路径标记
                path = behavior.get("path", [])
                for i, point in enumerate(path):
                    marker_x = base_x + point.get("dx", 0)
                    marker_z = base_z + point.get("dz", 0)
                    commands.append(
                        f"summon armor_stand {marker_x} {base_y} {marker_z} "
                        f"{{Invisible:1b,Marker:1b,CustomName:'\"patrol_point_{i}\"'}}"
                    )
            
            elif btype == "particle":
                # 粒子效果
                particle_type = behavior.get("particle", "end_rod")
                commands.append(
                    f"particle {particle_type} {base_x} {base_y + 1} {base_z} "
                    f"0.5 0.5 0.5 0.1 10 force"
                )
        
        return commands
    
    def get_behavior_context_for_ai(self, level_id: str) -> str:
        """
        获取NPC行为的上下文描述，用于AI对话生成
        """
        if level_id not in self.active_npcs:
            return ""
        
        npc_data = self.active_npcs[level_id]
        ai_hints = npc_data.get("ai_hints", "")
        behaviors = npc_data.get("behaviors", [])
        
        behavior_descriptions = []
        for b in behaviors:
            if b.get("description"):
                behavior_descriptions.append(f"- {b.get('description')}")
        
        context = f"""
【NPC性格与背景】
{ai_hints}

【NPC当前行为】
{chr(10).join(behavior_descriptions) if behavior_descriptions else "- 站立等待"}

【可触发的互动】
"""
        
        # 添加可触发的关键词提示
        for b in behaviors:
            if b.get("type") == "quest":
                keywords = ", ".join(b.get("trigger_keywords", []))
                context += f"- 任务「{b.get('quest_name')}」: 关键词包括 {keywords}\n"
        
        return context.strip()

    def _build_dialogue_node(self, dialogue: Any, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        meta = meta or {}

        def _normalize_script(candidate: Any) -> Optional[List[Dict[str, Any]]]:
            if not isinstance(candidate, list):
                return None
            script: List[Dict[str, Any]] = []
            for entry in candidate:
                if isinstance(entry, dict):
                    script.append({k: v for k, v in entry.items() if v is not None})
                elif isinstance(entry, str):
                    script.append({"op": "narrate", "text": entry})
            return script or None

        def _normalize_choices(candidate: Any) -> Optional[List[Dict[str, Any]]]:
            if not isinstance(candidate, list):
                return None
            choices: List[Dict[str, Any]] = []
            for option in candidate:
                if isinstance(option, dict):
                    label = option.get("label")
                    if label:
                        choices.append({k: v for k, v in option.items() if v is not None})
                elif isinstance(option, str):
                    choices.append({"label": option})
            return choices or None

        node: Dict[str, Any]
        if isinstance(dialogue, dict):
            node = {k: v for k, v in dialogue.items() if v is not None}
        elif isinstance(dialogue, list):
            text = "\n".join(str(line) for line in dialogue if line is not None)
            node = {"text": text}
        elif isinstance(dialogue, str):
            node = {"text": dialogue}
        else:
            return None

        base_title = meta.get("dialogue_title") or node.get("title")
        node["title"] = base_title or "NPC 对话"

        base_type = node.get("type") or meta.get("dialogue_type") or "npc_dialogue"
        node["type"] = base_type

        script = _normalize_script(node.get("script")) or _normalize_script(meta.get("dialogue_script"))
        if script:
            node["script"] = script
        else:
            node.pop("script", None)

        choices = _normalize_choices(node.get("choices")) or _normalize_choices(meta.get("dialogue_choices"))
        if choices:
            node["choices"] = choices
        else:
            node.pop("choices", None)

        hint = meta.get("dialogue_hint")
        if hint and "hint" not in node:
            node["hint"] = hint

        text = node.get("text")
        if text is not None:
            node["text"] = str(text)
        elif "text" in node:
            node.pop("text")

        return node

    def _merge_world_patch(self, base: Optional[Dict[str, Any]], addition: Dict[str, Any]) -> Dict[str, Any]:
        if not addition:
            return dict(base or {})
        merged = dict(base or {})
        for key, value in addition.items():
            if key == "mc" and isinstance(value, dict):
                existing = merged.get("mc")
                if isinstance(existing, dict):
                    merged["mc"] = {**existing, **value}
                else:
                    merged["mc"] = dict(value)
            else:
                merged[key] = value
        return merged


# 全局实例
npc_engine = NPCBehaviorEngine()

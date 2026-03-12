"""Utilities for synthesizing flagship-format levels from natural language prompts."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

__all__ = ["generate_flagship_level"]


@dataclass
class ActionSpec:
    """Structured description of an inferred player task action."""

    token: str
    milestone_id: str
    title: str
    hint: str
    phrase: str
    category: str
    memory_flag: str
    particle: str
    particle_count: int
    chat: str
    condition_title: str


ACTION_KEYWORDS = [
    (re.compile("探索|寻找|前进|穿过|踏入|行走|漫步|走进"), "explore"),
    (re.compile("对话|交谈|触碰|点亮|启动|拥抱|交流|呼唤|安抚|陪伴"), "interact"),
    (re.compile("倾听|聆听|记忆|回忆|凝视|感受|思索|冥想|体会"), "reflect"),
    (re.compile("完成|守护|战胜|驱散|解锁|修复|收集|结束"), "resolve"),
]

CATEGORY_DEFS: Dict[str, Dict[str, object]] = {
    "explore": {
        "title": "探索轨迹",
        "hint": "追随玩家描绘的足迹，探索新的空间。",
        "particle": "happy_villager",
        "count": 18,
        "beat": "✨ 你踏入玩家描绘的世界，新的线索正在浮现。",
    },
    "interact": {
        "title": "互动节点",
        "hint": "与场景中的角色或物件互动，让故事继续前进。",
        "particle": "note",
        "count": 16,
        "beat": "🎐 场景回应了你的动作，情绪在空气中回荡。",
    },
    "reflect": {
        "title": "情绪回响",
        "hint": "静下心来倾听与回忆，记录此刻的感受。",
        "particle": "soul",
        "count": 14,
        "beat": "🌌 你的心绪与玩家的叙事产生了共鸣。",
    },
    "resolve": {
        "title": "仪式完成",
        "hint": "让故事顺势落幕，为玩家的章节画上句号。",
        "particle": "glow",
        "count": 20,
        "beat": "⚡ 故事的结点被点亮，新记忆被保存。",
    },
}

DEFAULT_FALLBACK_ORDER = ["explore", "interact", "reflect", "resolve"]
DEFAULT_ACTION_STRINGS = [
    "探索玩家描绘的起点。",
    "与记忆中的角色对话。",
    "完成这一章的情绪仪式。",
]


def _slugify(text: str, max_words: int = 4) -> str:
    tokens = re.findall(r"[\w\-]+", text.lower())
    if not tokens:
        return "vision"
    selected = tokens[:max_words]
    slug = "_".join(selected)
    sanitized = re.sub(r"[^a-z0-9_]+", "", slug)
    return sanitized[:48] or "vision"


def _derive_title(description: str, explicit_title: Optional[str] = None) -> str:
    if explicit_title:
        return explicit_title.strip()[:80]
    trimmed = description.strip()
    if len(trimmed) <= 18:
        return f"玩家创作 · {trimmed}"
    return f"玩家创作 · {trimmed[:18]}…"


def _derive_tags(description: str, extra_tags: Optional[List[str]] = None) -> List[str]:
    tags: List[str] = ["user", "generated", "flagship"]
    if extra_tags:
        for tag in extra_tags:
            token = str(tag).strip().lower()
            if token and token not in tags:
                tags.append(token)
    mood_tokens = re.findall(r"月亮|夜|雨|雪|桥|花|海|山|梦|记忆", description)
    mapping = {
        "月亮": "moon",
        "夜": "night",
        "雨": "rain",
        "雪": "snow",
        "桥": "bridge",
        "花": "flower",
        "海": "sea",
        "山": "mountain",
        "梦": "dream",
        "记忆": "memory",
    }
    for tok in mood_tokens:
        mapped = mapping.get(tok)
        if mapped and mapped not in tags:
            tags.append(mapped)
    return tags


def _clean_fragment(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"[\s,，、;；]+$", "", cleaned)
    return cleaned


class TaskBuilder:
    """Infer quest tasks, milestones, and rule listeners from raw description."""

    def __init__(self, level_id: str, description: str, slug: str) -> None:
        self.level_id = level_id
        self.description = description
        self.slug = slug

    def build(self) -> Dict[str, object]:
        phrases = self._extract_phrases()
        categories = self._assign_categories(phrases)

        actions: List[ActionSpec] = []
        for idx, (phrase, category) in enumerate(zip(phrases, categories)):
            actions.append(self._make_action(idx, phrase, category))

        rule_refs = [action.token for action in actions]
        task = self._build_task(actions, rule_refs)
        listeners = [self._build_listener(action) for action in actions]
        beats = [self._build_beat(idx, action) for idx, action in enumerate(actions)]
        trigger_zones = [self._build_trigger_zone(idx, action) for idx, action in enumerate(actions)]

        return {
            "tasks": [task],
            "listeners": listeners,
            "beats": beats,
            "trigger_zones": trigger_zones,
            "memory_flags": sorted({action.memory_flag for action in actions}),
            "rule_refs": rule_refs,
            "actions": actions,
        }

    def _extract_phrases(self) -> List[str]:
        candidates = re.split(r"[。！？!?\n]+", self.description)
        phrases = []
        for raw in candidates:
            cleaned = _clean_fragment(raw)
            if len(cleaned) >= 4:
                phrases.append(cleaned)
        if not phrases:
            return list(DEFAULT_ACTION_STRINGS)
        if len(phrases) == 1:
            phrases.append("与描述中的情感对话。")
        if len(phrases) == 2:
            phrases.append("完成玩家剧情的仪式收束。")
        return phrases[:3]

    def _assign_categories(self, phrases: List[str]) -> List[str]:
        assigned: List[str] = []
        fallback_index = 0
        for phrase in phrases:
            category = None
            for pattern, candidate in ACTION_KEYWORDS:
                if pattern.search(phrase):
                    category = candidate
                    break
            if category is None:
                category = DEFAULT_FALLBACK_ORDER[fallback_index % len(DEFAULT_FALLBACK_ORDER)]
                fallback_index += 1
            assigned.append(category)
        return assigned

    def _make_action(self, index: int, phrase: str, category: str) -> ActionSpec:
        base = f"user_{self.slug}_{category}_{index + 1}"
        token = re.sub(r"[^a-z0-9_]", "", base)[:48]
        if not token:
            token = f"user_event_{index + 1:02d}"

        milestone_id = f"{self.level_id}_{category}_{index + 1:02d}"
        definition = CATEGORY_DEFS.get(category, CATEGORY_DEFS["explore"])

        fragment = phrase[:12] + "…" if len(phrase) > 12 else phrase
        title = definition["title"]
        title = f"{title} · {fragment}" if fragment else title
        hint_base = str(definition.get("hint", "跟随提示完成任务。"))
        hint = f"{hint_base}" if not fragment else f"{hint_base}（{fragment}）"

        particle = str(definition.get("particle", "glow"))
        particle_count = int(definition.get("count", 16))
        chat = str(definition.get("beat", f"✦ {title}"))
        memory_flag = f"user_memory_{category}"

        return ActionSpec(
            token=token,
            milestone_id=milestone_id,
            title=title,
            hint=hint,
            phrase=phrase,
            category=category,
            memory_flag=memory_flag,
            particle=particle,
            particle_count=particle_count,
            chat=chat,
            condition_title=fragment or title,
        )

    def _build_task(self, actions: List[ActionSpec], rule_refs: List[str]) -> Dict[str, object]:
        summary = " → ".join(action.title for action in actions)
        task_id = f"{self.level_id}_quest"
        return {
            "id": task_id,
            "type": "quest_event",
            "title": "玩家创作章节任务",
            "hint": summary or "跟随玩家创作的提示完成事件。",
            "rule_event": actions[-1].token if actions else None,
            "conditions": [
                {
                    "id": action.milestone_id,
                    "quest_event": action.token,
                    "count": 1,
                    "title": action.title,
                    "hint": action.hint,
                }
                for action in actions
            ],
            "rule_refs": rule_refs,
            "rewards": [
                {"type": "xp", "amount": 160},
                {"type": "item", "amount": 1, "data": {"id": "user_memory_shard"}},
            ],
            "dialogue": {
                "on_complete": "✨ 玩家创作的章节完成，新记忆被保存。",
            },
            "issue_node": {
                "title": "启动玩家创作任务",
                "text": "跟随事件提示，逐个完成玩家叙事中的关键节点。",
            },
        }

    def _build_listener(self, action: ActionSpec) -> Dict[str, object]:
        return {
            "id": action.token,
            "type": "quest_event",
            "targets": [action.token],
            "quest_event": action.token,
            "metadata": {
                "dialogue": [f"§d玩家章节事件§r · {action.title}"],
                "update_behaviors": [
                    {
                        "type": "particle",
                        "particle": action.particle,
                        "description": action.chat,
                    }
                ],
            },
        }

    def _build_beat(self, index: int, action: ActionSpec) -> Dict[str, object]:
        return {
            "id": f"user_action_{index + 1:02d}",
            "trigger": f"rule_event:{action.token}",
            "rule_refs": [action.token],
            "memory_set": [action.memory_flag],
            "world_patch": {
                "mc": {
                    "tell": action.chat,
                    "particle": {"type": action.particle, "count": action.particle_count},
                }
            },
        }

    def _build_trigger_zone(self, index: int, action: ActionSpec) -> Dict[str, object]:
        return {
            "id": f"{action.token}_zone",
            "label": action.title,
            "quest_event": action.token,
            "radius": 4.5 + index,
            "offset": {"dx": float(index * 2 - 1), "dy": 0.0, "dz": float(index - 1)},
        }


def generate_flagship_level(
    description: str,
    *,
    title: Optional[str] = None,
    extra_tags: Optional[List[str]] = None,
) -> Tuple[str, Dict[str, object]]:
    """Return a ``(level_id, level_json)`` tuple for the given description."""

    cleaned = (description or "").strip()
    if len(cleaned) < 12:
        raise ValueError("描述需要至少 12 个字符，以便生成有效的剧情线索。")

    slug = _slugify(cleaned)
    epoch_ms = int(time.time() * 1000)
    level_id = f"flagship_user_{epoch_ms}"
    derived_title = _derive_title(cleaned, explicit_title=title)
    tags = _derive_tags(cleaned, extra_tags)
    now = datetime.utcnow().isoformat() + "Z"

    narrative_text = [
        f"生成时间：{now}",
        cleaned,
    ]

    storyline_theme = f"user_created_{slug.split('_', 1)[0]}"
    emotional_vector = "player_authored"

    beats = [
        {
            "id": "user_intro",
            "trigger": "on_enter",
            "cinematic": "user_generated_entry",
            "rule_refs": ["user_intro"],
            "world_patch": {
                "mc": {
                    "tell": "✨ 这是玩家亲手绘制的场景，故事刚刚开始。",
                    "music": {"record": "otherside"},
                    "particle": {"type": "glow", "count": 18},
                }
            },
            "choices": [
                {
                    "id": "embrace_scene",
                    "text": "向前一步，拥抱玩家叙事。",
                    "rule_event": "user_choice_embrace",
                    "tags": ["embrace"],
                },
                {
                    "id": "observe_scene",
                    "text": "先观察这幅画面。",
                    "rule_event": "user_choice_observe",
                    "tags": ["observe"],
                },
            ],
        },
        {
            "id": "user_question",
            "trigger": "rule_event:user_choice_embrace",
            "rule_refs": ["user_forward"],
            "memory_set": ["user_memory_embrace"],
            "world_patch": {
                "mc": {
                    "tell": "💫 玩家世界回应了你的靠近。",
                    "particle": {"type": "happy_villager", "count": 16},
                }
            },
        },
        {
            "id": "user_linger",
            "trigger": "rule_event:user_choice_observe",
            "rule_refs": ["user_reflect"],
            "memory_set": ["user_memory_observe"],
            "world_patch": {
                "mc": {
                    "tell": "🌙 你在场景边缘徘徊，情绪在空气中缓慢流动。",
                    "particle": {"type": "dripping_water", "count": 22},
                }
            },
        },
        {
            "id": "user_outro",
            "trigger": "story:continue",
            "rule_refs": [],
            "next_level": None,
            "world_patch": {
                "mc": {
                    "tell": "✨ 玩家叙事完成本章，新的选择正在酝酿。",
                    "weather": "CLEAR",
                }
            },
        },
    ]

    scene = {
        "world": "KunmingLakeStory",
        "teleport": {"x": 4.5, "y": 70, "z": -3.5, "yaw": 180, "pitch": 0},
        "environment": {"weather": "CLEAR", "time": "SUNSET"},
        "structures": ["structures/generated/player_canvas.nbt"],
        "npc_skins": [
            {"id": "玩家影像", "skin": "skins/player_memory.png"},
        ],
    }

    world_patch = {
        "mc": {
            "_scene": {
                "level_id": level_id,
                "title": derived_title,
                "scene_world": "KunmingLakeStory",
                "featured_npc": "玩家影像",
            },
            "tell": cleaned[:120],
            "music": {"record": "otherside"},
            "particle": {"type": "portal", "count": 30},
        },
        "variables": {
            "theme": storyline_theme,
            "arc_position": "user_created",
            "generated_at": now,
        },
    }

    continuity = {
        "previous": "flagship_12",
        "next": None,
        "emotional_vector": emotional_vector,
        "arc_step": 0,
        "origin": "user_generated",
    }

    task_bundle = TaskBuilder(level_id, cleaned, slug).build()

    # Merge action-driven beats and triggers into base narrative/world patch.
    beats.extend(task_bundle["beats"])

    mc_patch = world_patch.setdefault("mc", {})
    existing_triggers = list(mc_patch.get("trigger_zones") or [])
    existing_triggers.extend(task_bundle["trigger_zones"])
    if existing_triggers:
        mc_patch["trigger_zones"] = existing_triggers

    npc_events = list(mc_patch.get("npc_trigger_events") or [])
    if task_bundle["actions"]:
        npc_events.append({"npc": "玩家影像", "quest_event": task_bundle["actions"][0].token})
        if len(task_bundle["actions"]) >= 2:
            npc_events.append({"npc": "玩家影像", "quest_event": task_bundle["actions"][-1].token})
    if npc_events:
        mc_patch["npc_trigger_events"] = npc_events

    rules_listeners = [
        {
            "id": "user_intro",
            "type": "quest_event",
            "targets": ["user_intro"],
            "quest_event": "user_intro",
        },
        {
            "id": "user_forward",
            "type": "quest_event",
            "targets": ["user_forward"],
            "quest_event": "user_forward",
        },
        {
            "id": "user_reflect",
            "type": "quest_event",
            "targets": ["user_reflect"],
            "quest_event": "user_reflect",
        },
    ]
    rules_listeners.extend(task_bundle["listeners"])

    level_payload: Dict[str, object] = {
        "id": level_id,
        "title": derived_title,
        "tags": tags,
        "meta": {
            "chapter": None,
            "word_count": len(cleaned),
            "source": "player",
            "created_at": now,
        },
        "storyline_theme": storyline_theme,
        "continuity": continuity,
        "memory_affinity": task_bundle["memory_flags"],
        "narrative": {
            "text": narrative_text,
            "beats": beats,
        },
        "scene": scene,
        "world_patch": world_patch,
        "rules": {
            "listeners": rules_listeners,
        },
        "tasks": task_bundle["tasks"],
        "exit": {
            "phrase_aliases": ["离开玩家创作", "退出玩家章节", "return hub"],
            "return_spawn": "KunmingLakeHub",
            "teleport": {"x": 128.5, "y": 72, "z": -16.5, "yaw": 180, "pitch": 0},
        },
    }

    return level_id, level_payload

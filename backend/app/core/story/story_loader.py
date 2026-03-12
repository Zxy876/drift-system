# backend/app/core/story/story_loader.py
import os, json
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Set, Tuple

# backend/app/core/story/story_loader.py
# __file__ = backend/app/core/story/story_loader.py
# 往上三层到 backend/
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)


# Primary storyline content now lives under `flagship_levels`.
PRIMARY_DIR_NAME = "flagship_levels"
DATA_DIR = os.path.join(BACKEND_DIR, "data", PRIMARY_DIR_NAME)

TUTORIAL_CANONICAL_ID = "flagship_tutorial"
TUTORIAL_ALIASES = {
    "level_01",
    "level_1",
    "level1",
    "level-01",
    "level01",
    "tutorial",
    "tutorial_level",
    "level_tutorial",
    "kunminglaketutorial",
    "kunminglake_tutorial",
    "tutorial_spawn",
    "tutorial_level_v1",
}


@dataclass
class Level:
    level_id: str
    title: str
    text: List[str]
    tags: List[str]
    mood: Dict[str, Any]
    choices: List[Dict[str, Any]]
    meta: Dict[str, Any]
    npcs: List[Dict[str, Any]]
    bootstrap_patch: Dict[str, Any]
    tree: Optional[Dict[str, Any]] = None


def _iter_level_files(include_legacy: bool = True):
    """Yield ``(directory, filename, source)`` tuples in priority order."""

    _ = include_legacy  # legacy paths removed but retained for signature compatibility

    if not DATA_DIR or not os.path.exists(DATA_DIR):
        return

    entries: List[Tuple[str, str, str]] = []

    for dirpath, _, filenames in os.walk(DATA_DIR):
        rel_dir = os.path.relpath(dirpath, DATA_DIR)
        primary_segment = rel_dir.split(os.sep)[0] if rel_dir != "." else ""
        if primary_segment == "generated":
            source = "generated"
        else:
            source = "flagship"

        for filename in filenames:
            if not filename.endswith(".json") or filename.startswith("_"):
                continue
            entries.append((dirpath, filename, source))

    seen: Set[str] = set()
    for directory, filename, source in sorted(entries, key=lambda item: (0 if os.path.relpath(item[0], DATA_DIR) == "." else 1, item[0], item[1])):
        key = f"{directory}:{filename}"
        if key in seen:
            continue
        seen.add(key)
        yield directory, filename, source


def _find_level_path(filename: str) -> Optional[str]:
    if not DATA_DIR or not os.path.exists(DATA_DIR):
        return None

    direct_path = os.path.join(DATA_DIR, filename)
    if os.path.exists(direct_path):
        return direct_path

    for dirpath, _, _ in os.walk(DATA_DIR):
        candidate = os.path.join(dirpath, filename)
        if os.path.exists(candidate):
            return candidate
    return None


def _canonical_filename(level_id: str) -> str:
    base = level_id[:-5] if level_id.endswith(".json") else level_id
    return f"{base}.json"


def _candidate_filenames(level_id: str) -> List[str]:
    """Generate filename candidates for a requested level id.

    Primary storyline files use the ``flagship_`` prefix. Callers migrating
    from legacy ``level_XX`` ids are still mapped onto the flagship namespace
    before falling back to their literal value.
    """

    base = level_id[:-5] if level_id.endswith(".json") else level_id
    candidates: List[str] = []

    lowered = base.lower()


    if lowered in TUTORIAL_ALIASES:
        candidates.append(f"{TUTORIAL_CANONICAL_ID}.json")

    if base.startswith("flagship_"):
        candidates.append(f"{base}.json")
    elif base.startswith("level_"):
        suffix = base.split("_", 1)[1]
        if suffix:
            normalized = suffix
            if suffix.isdigit():
                normalized = f"{int(suffix):02d}"
            remapped = f"flagship_{normalized}"
            candidates.append(f"{remapped}.json")
    else:
        # For custom content (玩家生成关卡等) 仍允许按原名加载。
        candidates.append(f"{base}.json")

    # Deduplicate while preserving order.
    seen: Set[str] = set()
    ordered: List[str] = []
    for name in candidates:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def list_levels() -> List[Dict[str, Any]]:
    """返回剧情关卡元数据列表。"""
    levels = []
    for directory, fn, source in _iter_level_files(include_legacy=True):
        path = os.path.join(directory, fn)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            levels.append({
                "id": data.get("id", fn.replace(".json", "")),
                "title": data.get("title", ""),
                "file": fn,
                "tags": data.get("tags", []),
                "chapter": (data.get("meta") or {}).get("chapter"),
                "word_count": (data.get("meta") or {}).get("word_count"),
                "source": source,
                "deprecated": False,
            })
        except Exception as e:
            levels.append({
                "id": fn.replace(".json", ""),
                "title": f"[BROKEN] {fn}",
                "file": fn,
                "source": source,
                "deprecated": False,
                "error": str(e)
            })
    return levels


def load_level(level_id: str) -> Level:
    """读取单个关卡定义，优先选择旗舰剧情集合。"""

    for candidate in _candidate_filenames(level_id):
        path = _find_level_path(candidate)
        if path:
            file_id = os.path.splitext(os.path.basename(path))[0]
            return _load_level_file(path, file_id, level_id)

    raise FileNotFoundError(
        f"Level file not found for id '{level_id}' in {DATA_DIR}"
    )


def _load_level_file(path: str, file_id: str, requested_id: str) -> Level:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 兼容 text 是 list / 或 string
    raw_text = data.get("text", [])
    if isinstance(raw_text, str):
        text_list = [raw_text]
    else:
        text_list = list(raw_text)

    # npcs / world_patch / tree 可能不存在
    npcs = data.get("npcs", []) or []
    # 优先使用 world_patch (增强配置)，fallback 到 bootstrap_patch
    world_patch = data.get("world_patch") or data.get("bootstrap_patch", {
        "variables": {},
        "mc": {"tell": f"关卡 {data.get('title','')} 已加载。"}
    })
    tree = data.get("tree")

    level_identifier = data.get("id") or file_id or requested_id

    level = Level(
        level_id=level_identifier,
        title=data.get("title", level_identifier),
        text=text_list,
        tags=data.get("tags", []),
        mood=data.get("mood", {"base":"calm","intensity":0.5}),
        choices=data.get("choices", []),
        meta=data.get("meta", {}),
        npcs=npcs,
        bootstrap_patch=world_patch,  # 使用world_patch作为bootstrap_patch
        tree=tree
    )

    # Preserve the raw payload so extension parsers can access structured metadata.
    setattr(level, "_raw_payload", data)

    if level.level_id == TUTORIAL_CANONICAL_ID:
        setattr(level, "legacy_ids", sorted(TUTORIAL_ALIASES))

    return level


def build_level_prompt(level: Level) -> str:
    """
    把心悦文集文章转成 AI 的关卡系统提示词。
    """
    npc_lines = []
    for n in level.npcs:
        npc_lines.append(
            f"- NPC: {n.get('name','未知')} "
            f"(type={n.get('type','villager')}, role={n.get('role','人物')}) "
            f"personality={n.get('personality','')}"
        )
    npc_block = "\n".join(npc_lines) if npc_lines else "- 本关暂无固定NPC"

    text_block = "\n".join(level.text)

    prompt = f"""
【关卡ID】{level.level_id}
【关卡标题】{level.title}

【心悦文集原文（世界观与剧情核）】
{text_block}

【固定NPC（文章主人公/配角的灵魂）】
{npc_block}

【规则】
- 你必须让剧情与原文情绪、人物关系一致，但允许玩家干预与分支。
- 玩家可选择“接受/拒绝/折中”你的剧情推进；你要给出清晰的 option 与 node。
- 如果本关 meta/choices 给了固定出口，也可以用它当作“主线终点”参考。
""".strip()

    return prompt
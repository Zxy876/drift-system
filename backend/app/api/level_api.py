from fastapi import APIRouter, HTTPException
import json
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.story.story_loader import DATA_DIR, load_level
from app.core.story.story_engine import story_engine
from app.core.story.level_schema import ensure_level_extensions

try:
    # Prefer loading from the top-level backend package when available (test contexts).
    from backend.enhance_generated_level import generate_flagship_level
except ImportError:  # pragma: no cover - production runtime invoked from backend dir
    from enhance_generated_level import generate_flagship_level

router = APIRouter()

LEVEL_DIR = Path(DATA_DIR)


class GenerateLevelRequest(BaseModel):
    description: str = Field(..., min_length=12, max_length=2048)
    title: Optional[str] = Field(default=None, max_length=80)
    tags: Optional[List[str]] = None


@router.post("/world/story/generate-level")
async def generate_story_level(payload: GenerateLevelRequest):

    try:
        level_id, level_payload = generate_flagship_level(
            payload.description,
            title=payload.title,
            extra_tags=payload.tags,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    generated_dir = LEVEL_DIR / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{level_id}.json"
    filepath = generated_dir / filename

    counter = 1
    while filepath.exists():
        filepath = generated_dir / f"{level_id}_{counter}.json"
        counter += 1

    with filepath.open("w", encoding="utf-8") as f:
        json.dump(level_payload, f, ensure_ascii=False, indent=2)

    story_engine.register_generated_level(level_payload.get("id", level_id))

    try:
        level = load_level(level_payload.get("id", level_id))
        ensure_level_extensions(level, level_payload)
        story_engine.register_rule_listeners(level)
    except FileNotFoundError:
        # The reload did not materialize the level file; skip runtime registration.
        pass
    except Exception as exc:  # noqa: BLE001 - surface for diagnostics without failing the API
        print(f"[LevelAPI] failed to register rule listeners for {level_id}: {exc}")

    return {
        "status": "ok",
        "level_id": level_payload.get("id", level_id),
        "path": str(filepath),
        "tags": level_payload.get("tags", []),
        "storyline_theme": level_payload.get("storyline_theme"),
    }


@router.post("/story/inject")
async def inject_story_level(level_id: str, title: str, text: str):

    LEVEL_DIR.mkdir(parents=True, exist_ok=True)

    target_id = level_id.strip()
    if target_id.endswith(".json"):
        target_id = target_id[:-5]
    lower_id = target_id.lower()
    if not lower_id.startswith("flagship_"):
        if lower_id.startswith("level_"):
            suffix = target_id.split("_", 1)[1]
            target_id = f"flagship_{suffix}"
        else:
            target_id = f"flagship_{target_id}"

    filepath = LEVEL_DIR / f"{target_id}.json"

    data = {
        "title": title,
        "text": text,
        "options": [],
        "world_patch": {
            "mc": {
                "spawn": {
                    "type": "villager",
                    "name": "剧情NPC",
                    "offset": {"dx": 3, "dy": 0, "dz": 3}
                },
                "build": {
                    "shape": "platform",
                    "size": 5,
                    "material": "stone"
                },
                "tell": f"✨ 欢迎来到【{title}】"
            }
        }
    }

    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    story_engine.register_generated_level(target_id)

    return {
        "status": "ok",
        "level_id": target_id,
        "path": str(filepath)
    }

@router.post("/story/inject")
async def inject_story_level(level_id: str, title: str, text: str):

    LEVEL_DIR.mkdir(parents=True, exist_ok=True)

    target_id = level_id.strip()
    if target_id.endswith(".json"):
        target_id = target_id[:-5]
    lower_id = target_id.lower()
    if not lower_id.startswith("flagship_"):
        if lower_id.startswith("level_"):
            suffix = target_id.split("_", 1)[1]
            target_id = f"flagship_{suffix}"
        else:
            target_id = f"flagship_{target_id}"

    filepath = LEVEL_DIR / f"{target_id}.json"

    # 为新关卡创建一个独特的场景配置
    data = {
        "title": title,
        "text": text,
        "options": [],
        "world_patch": {
            "mc": {
                "spawn": {
                    "type": "villager",
                    "name": "剧情NPC",
                    "offset": {"dx": 3, "dy": 0, "dz": 3}
                },
                "build": {
                    "shape": "platform",
                    "size": 5,
                    "material": "stone"
                },
                "tell": f"✨ 欢迎来到【{title}】"
            }
        }
    }

    with filepath.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {
        "status": "ok",
        "level_id": target_id,
        "path": str(filepath)
    }
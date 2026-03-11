from __future__ import annotations

import os
import threading
from typing import Any, Dict

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/settings", tags=["Settings"])


def _read_float_env(name: str, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return float(raw)
    except (TypeError, ValueError):
        return fallback


def _read_int_env(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return fallback


def _read_bool_env(name: str, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    token = str(raw).strip().lower()
    return token in {"1", "true", "yes", "on"}


class GenerationPolicy(BaseModel):
    scene_cooldown: float = Field(..., ge=0)
    spawn_probability: float = Field(..., ge=0, le=1)
    max_scenes_per_hour: int = Field(..., ge=1)
    spawn_distance: float = Field(..., ge=0)
    require_player_movement: bool
    require_new_location: bool


_policy_lock = threading.Lock()
_generation_policy: Dict[str, Any] = {
    "scene_cooldown": max(0.0, _read_float_env("DRIFT_SCENE_COOLDOWN", 60.0)),
    "spawn_probability": min(1.0, max(0.0, _read_float_env("DRIFT_SCENE_SPAWN_PROBABILITY", 0.4))),
    "max_scenes_per_hour": max(1, _read_int_env("DRIFT_SCENE_MAX_PER_HOUR", 5)),
    "spawn_distance": max(0.0, _read_float_env("DRIFT_SCENE_SPAWN_DISTANCE", 40.0)),
    "require_player_movement": _read_bool_env("DRIFT_SCENE_REQUIRE_PLAYER_MOVEMENT", True),
    "require_new_location": _read_bool_env("DRIFT_SCENE_REQUIRE_NEW_LOCATION", True),
}


def get_generation_policy_snapshot() -> Dict[str, Any]:
    with _policy_lock:
        return dict(_generation_policy)


def _policy_payload() -> Dict[str, Any]:
    return get_generation_policy_snapshot()


@router.get("/generation", response_model=GenerationPolicy)
def get_generation_policy() -> Dict[str, Any]:
    return _policy_payload()


@router.post("/generation", response_model=GenerationPolicy)
def update_generation_policy(payload: GenerationPolicy) -> Dict[str, Any]:
    validated = payload.model_dump()
    with _policy_lock:
        _generation_policy.update(validated)
        return dict(_generation_policy)

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List


CONTENT_DIR = Path(__file__).resolve().parents[2] / "content" / "story"
NARRATIVE_POLICY_FILE = CONTENT_DIR / "narrative_policy.json"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _default_policy() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "weights": {
            "scene_match": 3,
            "event_match": 2,
            "asset_match": 2,
            "level_match": 1,
        },
        "tie_break_order": [
            "priority",
            "target_node_lexicographic",
        ],
    }


def _normalize_tie_break_order(raw_value: Any) -> List[str]:
    valid_tokens = {"priority", "target_node_lexicographic"}
    rows: List[str] = []
    seen = set()
    for item in raw_value if isinstance(raw_value, list) else []:
        token = str(item or "").strip().lower()
        if token in valid_tokens and token not in seen:
            seen.add(token)
            rows.append(token)

    if not rows:
        rows = ["priority", "target_node_lexicographic"]
    return rows


@lru_cache(maxsize=1)
def load_narrative_policy() -> Dict[str, Any]:
    policy = _default_policy()

    if NARRATIVE_POLICY_FILE.exists() and NARRATIVE_POLICY_FILE.is_file():
        try:
            loaded = json.loads(NARRATIVE_POLICY_FILE.read_text(encoding="utf-8"))
        except Exception:
            loaded = None

        if isinstance(loaded, dict):
            weights = policy.get("weights") if isinstance(policy.get("weights"), dict) else {}
            loaded_weights = loaded.get("weights") if isinstance(loaded.get("weights"), dict) else {}

            merged_weights = {
                "scene_match": _safe_int(loaded_weights.get("scene_match"), _safe_int(weights.get("scene_match"), 3)),
                "event_match": _safe_int(loaded_weights.get("event_match"), _safe_int(weights.get("event_match"), 2)),
                "asset_match": _safe_int(loaded_weights.get("asset_match"), _safe_int(weights.get("asset_match"), 2)),
                "level_match": _safe_int(loaded_weights.get("level_match"), _safe_int(weights.get("level_match"), 1)),
            }
            policy = {
                "version": str(loaded.get("version") or policy.get("version") or "1.0"),
                "weights": merged_weights,
                "tie_break_order": _normalize_tie_break_order(loaded.get("tie_break_order")),
            }

    return policy

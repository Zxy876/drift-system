from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.core.narrative.semantic_engine import infer_semantic_from_text
from app.core.semantic.semantic_registry import get_semantic_registry, normalize_semantic_item_id


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace("-", "_").replace(" ", "_").strip("_")


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_keywords(values: Iterable[str] | None) -> List[str]:
    if not values:
        return []

    rows: List[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        rows.append(token)
    return rows


POETRY_CONCEPT_KEYWORDS: Dict[str, List[str]] = {
    "moon": ["月", "月亮", "月光", "moon", "lunar"],
    "night": ["夜", "夜色", "夜晚", "night", "midnight", "星"],
    "wind": ["风", "风声", "风起", "wind", "breeze", "gale"],
    "mist": ["雾", "雾气", "薄雾", "mist", "fog"],
    "rain": ["雨", "雨声", "雨滴", "rain", "storm"],
    "boat": ["舟", "船", "渡", "boat", "ferry"],
    "forest": ["林", "森林", "树林", "forest", "woods", "grove"],
    "dream": ["梦", "梦境", "dream", "sleep"],
    "memory": ["忆", "记忆", "回忆", "memory", "echo"],
    "light": ["灯", "烛", "光", "light", "lantern"],
    "fire": ["火", "篝火", "火光", "fire", "flame"],
    "water": ["海", "河", "湖", "潮", "water", "sea", "river"],
    "story": ["诗", "故事", "传说", "story", "poem", "verse"],
}


SAFE_RESOURCE_ALLOWLIST: set[str] = {
    "torch",
    "lantern",
    "campfire",
    "water",
    "stone",
    "cobblestone",
    "stone_bricks",
    "bookshelf",
    "paper",
    "chest",
    "barrel",
    "furnace",
}


CONCEPT_RESOURCE_WEIGHTS: Dict[str, Dict[str, int]] = {
    "moon": {"lantern": 3, "bookshelf": 1, "water": 1},
    "night": {"lantern": 2, "torch": 2, "campfire": 1},
    "wind": {"torch": 2, "paper": 2, "lantern": 1},
    "mist": {"water": 3, "lantern": 1},
    "rain": {"water": 3, "stone": 1},
    "boat": {"water": 3, "stone": 2},
    "forest": {"campfire": 2, "stone": 2, "torch": 1},
    "dream": {"lantern": 2, "bookshelf": 2, "paper": 1},
    "memory": {"bookshelf": 2, "lantern": 1, "chest": 1},
    "light": {"lantern": 3, "torch": 2, "campfire": 1},
    "fire": {"campfire": 3, "torch": 2, "furnace": 1},
    "water": {"water": 3, "stone": 1},
    "story": {"bookshelf": 3, "paper": 2, "lantern": 1},
    "travel": {"paper": 1, "stone": 1},
    "trade": {"barrel": 2, "chest": 2, "lantern": 1},
    "explore": {"torch": 2, "cobblestone": 2},
}


THEME_BY_CONCEPT: Dict[str, str] = {
    "moon": "lunar_grove",
    "night": "lunar_grove",
    "mist": "lunar_grove",
    "rain": "dock",
    "boat": "dock",
    "water": "dock",
    "wind": "camp",
    "forest": "camp",
    "fire": "camp",
    "light": "camp",
    "memory": "library",
    "dream": "library",
    "story": "library",
    "trade": "trade_post",
    "explore": "mine",
    "travel": "road",
}


FALLBACK_RESOURCE_WEIGHTS: Dict[str, int] = {
    "lantern": 3,
    "campfire": 2,
    "stone": 2,
}


def extract_poetry_concepts(poem: str) -> Dict[str, Any]:
    normalized = _normalize_text(poem)
    score_by_concept: Dict[str, int] = {}
    hits_by_concept: Dict[str, List[str]] = {}

    if normalized:
        for concept, keywords in POETRY_CONCEPT_KEYWORDS.items():
            score = 0
            hits: List[str] = []
            for keyword in keywords:
                keyword_token = str(keyword or "").strip().lower()
                if not keyword_token:
                    continue
                match_count = normalized.count(keyword_token)
                if match_count <= 0:
                    continue
                score += int(match_count)
                hits.append(str(keyword))

            if score > 0:
                score_by_concept[concept] = int(score_by_concept.get(concept, 0)) + int(score)
                hits_by_concept.setdefault(concept, [])
                hits_by_concept[concept].extend(hits)

    semantic_payload = infer_semantic_from_text(poem)
    all_scores = semantic_payload.get("all_scores") if isinstance(semantic_payload.get("all_scores"), dict) else {}
    for key, value in all_scores.items():
        concept = _normalize_token(key)
        amount = _safe_int(value, 0)
        if not concept or amount <= 0:
            continue
        bonus = max(1, amount // 3)
        score_by_concept[concept] = int(score_by_concept.get(concept, 0)) + int(bonus)
        hits_by_concept.setdefault(concept, []).append("$semantic_engine")

    semantic_name = _normalize_token(semantic_payload.get("semantic"))
    semantic_score = _safe_int(semantic_payload.get("score"), 0)
    if semantic_name and semantic_score > 0:
        score_by_concept[semantic_name] = int(score_by_concept.get(semantic_name, 0)) + max(1, semantic_score // 4)
        hits_by_concept.setdefault(semantic_name, []).append("$semantic_engine_top")

    if not score_by_concept:
        score_by_concept["story"] = 1
        hits_by_concept["story"] = ["$fallback"]

    concept_rows = [
        {
            "concept": concept,
            "score": score,
            "hits": _normalize_keywords(hits_by_concept.get(concept)),
        }
        for concept, score in score_by_concept.items()
        if int(score) > 0
    ]
    concept_rows.sort(key=lambda row: (-int(row.get("score") or 0), str(row.get("concept") or "")))

    return {
        "concepts": concept_rows,
        "concept_scores": dict(score_by_concept),
        "semantic_engine": {
            "semantic": semantic_payload.get("semantic"),
            "predicted_root": semantic_payload.get("predicted_root"),
            "score": _safe_int(semantic_payload.get("score"), 0),
            "all_scores": dict(all_scores),
            "matched_keywords": list(semantic_payload.get("matched_keywords") or []),
        },
    }


def _registry_concept_resources(concept: str, score: int, *, limit_per_concept: int = 3) -> List[tuple[str, int]]:
    concept_token = _normalize_token(concept)
    if not concept_token or score <= 0:
        return []

    try:
        registry = get_semantic_registry()
        item_ids = registry.list_items() if hasattr(registry, "list_items") else []
    except Exception:
        return []

    rows: List[tuple[str, int]] = []
    seen: set[str] = set()

    for item_id in item_ids:
        try:
            resolved = registry.resolve(item_id) if hasattr(registry, "resolve") else None
        except Exception:
            resolved = None

        if not isinstance(resolved, dict):
            continue

        tags = resolved.get("semantic_tags") if isinstance(resolved.get("semantic_tags"), list) else []
        normalized_tags = {_normalize_token(tag) for tag in tags if _normalize_token(tag)}
        if concept_token not in normalized_tags:
            continue

        normalized_item = normalize_semantic_item_id(item_id)
        if not normalized_item:
            continue

        if ":" in normalized_item:
            suffix = normalized_item.split(":", 1)[1]
        else:
            suffix = normalized_item

        resource_token = suffix if suffix in SAFE_RESOURCE_ALLOWLIST else normalized_item
        if resource_token not in SAFE_RESOURCE_ALLOWLIST:
            continue
        if resource_token in seen:
            continue

        seen.add(resource_token)
        rows.append((resource_token, max(1, score - len(rows))))
        if len(rows) >= max(1, int(limit_per_concept)):
            break

    return rows


def build_poetry_resources(
    concept_scores: Dict[str, Any],
    *,
    player_tag_rows: List[Dict[str, Any]] | None = None,
    max_resources: int = 12,
) -> Dict[str, Any]:
    normalized_max = max(1, min(48, _safe_int(max_resources, 12)))
    resources: Dict[str, int] = {}
    traces: Dict[str, List[Dict[str, Any]]] = {}

    def _add_resource(resource_id: str, amount: int, *, source: str, reason: str) -> None:
        token = normalize_semantic_item_id(resource_id)
        if not token or amount <= 0:
            return
        if token not in SAFE_RESOURCE_ALLOWLIST:
            return

        resources[token] = int(resources.get(token, 0)) + int(amount)
        traces.setdefault(token, []).append(
            {
                "source": source,
                "reason": reason,
                "delta": int(amount),
            }
        )

    normalized_scores: Dict[str, int] = {}
    for key, value in (concept_scores or {}).items():
        token = _normalize_token(key)
        amount = _safe_int(value, 0)
        if token and amount > 0:
            normalized_scores[token] = amount

    for concept, score in normalized_scores.items():
        mapped_resources = CONCEPT_RESOURCE_WEIGHTS.get(concept) or {}
        for resource_id, weight in mapped_resources.items():
            _add_resource(
                resource_id,
                int(score) * max(1, _safe_int(weight, 1)),
                source="concept_map",
                reason=concept,
            )

        for resource_id, bonus in _registry_concept_resources(concept, score):
            _add_resource(
                resource_id,
                bonus,
                source="semantic_registry",
                reason=concept,
            )

    tag_matches: List[Dict[str, Any]] = []
    for row in player_tag_rows or []:
        if not isinstance(row, dict):
            continue

        tag = _normalize_token(row.get("tag"))
        resource_id = normalize_semantic_item_id(row.get("resource_id"))
        if not tag or not resource_id:
            continue

        if ":" in resource_id:
            suffix = resource_id.split(":", 1)[1]
        else:
            suffix = resource_id

        resource_token = suffix if suffix in SAFE_RESOURCE_ALLOWLIST else resource_id
        if resource_token not in SAFE_RESOURCE_ALLOWLIST:
            continue

        matched_concepts: List[str] = []
        accumulated_boost = 0

        for concept, score in normalized_scores.items():
            if concept == tag or concept in tag or tag in concept:
                matched_concepts.append(concept)
                accumulated_boost += max(1, int(score) * 2)

        if accumulated_boost <= 0:
            continue

        _add_resource(
            resource_token,
            accumulated_boost,
            source="player_tag",
            reason=tag,
        )

        tag_matches.append(
            {
                "tag": tag,
                "resource_id": resource_token,
                "concepts": list(sorted(set(matched_concepts))),
                "delta": accumulated_boost,
            }
        )

    if not resources:
        for resource_id, amount in FALLBACK_RESOURCE_WEIGHTS.items():
            _add_resource(
                resource_id,
                amount,
                source="fallback",
                reason="default",
            )

    ranked = sorted(resources.items(), key=lambda row: (-int(row[1]), str(row[0])))
    ranked = ranked[:normalized_max]

    selected_resources: Dict[str, int] = {resource_id: int(score) for resource_id, score in ranked}
    selected_trace = {resource_id: list(traces.get(resource_id) or []) for resource_id, _ in ranked}

    source_stats: Dict[str, int] = {}
    for rows in selected_trace.values():
        for row in rows:
            source = str(row.get("source") or "unknown")
            source_stats[source] = int(source_stats.get(source, 0)) + 1

    return {
        "resources": selected_resources,
        "resource_trace": selected_trace,
        "source_stats": source_stats,
        "player_tag_matches": tag_matches,
    }


def suggest_poetry_scene_theme(
    concept_scores: Dict[str, Any],
    *,
    semantic_payload: Dict[str, Any] | None = None,
    explicit_theme: str | None = None,
) -> str:
    normalized_explicit = _normalize_token(explicit_theme)
    if normalized_explicit:
        return normalized_explicit

    ranked_concepts = sorted(
        (
            (_normalize_token(key), _safe_int(value, 0))
            for key, value in (concept_scores or {}).items()
            if _normalize_token(key) and _safe_int(value, 0) > 0
        ),
        key=lambda row: (-int(row[1]), str(row[0])),
    )

    for concept, _ in ranked_concepts:
        mapped_theme = _normalize_token(THEME_BY_CONCEPT.get(concept))
        if mapped_theme:
            return mapped_theme

    semantic_root = ""
    if isinstance(semantic_payload, dict):
        semantic_root = _normalize_token(semantic_payload.get("predicted_root"))
    if semantic_root:
        return semantic_root

    return "camp"


def default_poetry_scene_hint(poem: str, *, max_length: int = 120) -> str | None:
    rows = [str(row or "").strip() for row in str(poem or "").splitlines()]
    rows = [row for row in rows if row]
    if not rows:
        return None

    first_line = rows[0]
    if len(first_line) <= max_length:
        return first_line
    return f"{first_line[:max_length].rstrip()}…"

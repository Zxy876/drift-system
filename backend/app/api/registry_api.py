from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.semantic.player_tag_store import player_tag_store
from app.core.semantic.semantic_registry import get_semantic_registry


router = APIRouter(prefix="/registry", tags=["Registry"])


class PlayerTagUpsertRequest(BaseModel):
    player_id: str | None = Field(default=None)
    player: str | None = Field(default=None)
    tag: str = Field(..., min_length=1)
    resource_id: str | None = Field(default=None)
    resource: str | None = Field(default=None)
    resource_type: str | None = Field(default=None)
    namespace: str | None = Field(default=None)
    source: str | None = Field(default=None)


class PlayerTagDeleteRequest(BaseModel):
    id: int | None = Field(default=None)
    player_id: str | None = Field(default=None)
    player: str | None = Field(default=None)
    tag: str | None = Field(default=None)


def _normalize_token(value: Any) -> str:
    token = str(value or "").strip().lower()
    if not token:
        return ""
    return token.replace(" ", "_").replace("-", "_")


def _normalize_source_mode(value: Any) -> str:
    token = str(value or "all").strip().lower()
    if token in {"registry", "local", "semantic_registry"}:
        return "registry"
    if token in {"proxy", "external", "misode"}:
        return "proxy"
    return "all"


def _resource_namespace(resource_id: str, fallback: Any = None) -> str:
    fallback_token = _normalize_token(fallback)
    if fallback_token:
        return fallback_token

    normalized_resource = _normalize_token(resource_id)
    if ":" in normalized_resource:
        namespace = normalized_resource.split(":", 1)[0].strip()
        if namespace:
            return namespace

    return "minecraft"


def _resource_type(value: Any = None) -> str:
    token = _normalize_token(value)
    return token or "item"


def _group_player_tags(items: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    seen: Dict[str, set[str]] = {}

    for item in items:
        tag = str(item.get("tag") or "").strip()
        resource_id = str(item.get("resource_id") or "").strip()
        if not tag or not resource_id:
            continue

        if tag not in grouped:
            grouped[tag] = []
            seen[tag] = set()

        if resource_id in seen[tag]:
            continue

        seen[tag].add(resource_id)
        grouped[tag].append(resource_id)

    return grouped


def _resource_match_score(query: str, resource_id: str, tags: List[str], label: str | None = None) -> int:
    normalized_query = _normalize_token(query)
    if not normalized_query:
        return 0

    normalized_resource = _normalize_token(resource_id)
    score = 0

    if normalized_resource == normalized_query:
        score = max(score, 100)
    elif normalized_resource.startswith(normalized_query):
        score = max(score, 80)
    elif normalized_query in normalized_resource:
        score = max(score, 60)

    for tag in tags:
        normalized_tag = _normalize_token(tag)
        if not normalized_tag:
            continue
        if normalized_tag == normalized_query:
            score = max(score, 55)
        elif normalized_query in normalized_tag:
            score = max(score, 40)

    normalized_label = _normalize_token(label)
    if normalized_label:
        if normalized_label == normalized_query:
            score = max(score, 50)
        elif normalized_query in normalized_label:
            score = max(score, 35)

    return score


def _search_local_registry(query: str, limit: int) -> List[Dict[str, Any]]:
    registry = get_semantic_registry()
    item_ids = registry.list_items() if hasattr(registry, "list_items") else []
    item_set = set(item_ids)

    rows: List[Dict[str, Any]] = []
    for item_id in item_ids:
        normalized_item = _normalize_token(item_id)
        if not normalized_item:
            continue

        if ":" not in normalized_item and f"minecraft:{normalized_item}" in item_set:
            continue

        resolved = registry.resolve(normalized_item) if hasattr(registry, "resolve") else None
        resolved_map = dict(resolved) if isinstance(resolved, dict) else {}
        semantic_tags = [
            _normalize_token(tag)
            for tag in (resolved_map.get("semantic_tags") or [])
            if _normalize_token(tag)
        ]
        source = str(resolved_map.get("source") or "semantic_registry")

        score = _resource_match_score(query, normalized_item, semantic_tags)
        if score <= 0:
            continue

        rows.append(
            {
                "resource_id": normalized_item,
                "resource_type": "item",
                "namespace": _resource_namespace(normalized_item),
                "source": source,
                "semantic_tags": semantic_tags,
                "_score": score,
            }
        )

    rows.sort(key=lambda row: (-int(row.get("_score", 0)), str(row.get("resource_id") or "")))
    return rows[:limit]


def _proxy_base_url() -> str:
    for key in ("DRIFT_RESOURCE_PROXY_BASE_URL", "DRIFT_RESOURCE_PROXY_BASE"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value.rstrip("/")
    return ""


def _extract_proxy_items(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("items", "results", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]

    return []


def _search_proxy_registry(query: str, limit: int) -> List[Dict[str, Any]]:
    base_url = _proxy_base_url()
    if not base_url:
        return []

    raw_path = str(os.environ.get("DRIFT_RESOURCE_PROXY_SEARCH_PATH") or "/search").strip() or "/search"
    search_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
    timeout_raw = os.environ.get("DRIFT_RESOURCE_PROXY_TIMEOUT")

    try:
        timeout_seconds = float(timeout_raw) if timeout_raw else 2.5
    except (TypeError, ValueError):
        timeout_seconds = 2.5

    try:
        response = httpx.get(
            f"{base_url}{search_path}",
            params={"q": query, "limit": limit},
            timeout=max(0.5, timeout_seconds),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []

    rows: List[Dict[str, Any]] = []
    for row in _extract_proxy_items(payload):
        resource_id = _normalize_token(
            row.get("resource_id")
            or row.get("item_id")
            or row.get("id")
            or row.get("resource")
            or row.get("name")
        )
        if not resource_id:
            continue

        semantic_tags = [
            _normalize_token(tag)
            for tag in (row.get("semantic_tags") or row.get("tags") or [])
            if _normalize_token(tag)
        ]
        label = str(row.get("label") or row.get("display_name") or row.get("title") or "").strip() or None

        score = _resource_match_score(query, resource_id, semantic_tags, label)
        if score <= 0:
            continue

        rows.append(
            {
                "resource_id": resource_id,
                "resource_type": _resource_type(row.get("resource_type") or row.get("type") or row.get("kind")),
                "namespace": _resource_namespace(resource_id, row.get("namespace")),
                "source": str(row.get("source") or row.get("provider") or "proxy"),
                "semantic_tags": semantic_tags,
                "label": label,
                "_score": score,
            }
        )

    rows.sort(key=lambda item: (-int(item.get("_score", 0)), str(item.get("resource_id") or "")))
    return rows[:limit]


def _merge_search_results(*groups: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    best_by_resource: Dict[str, Dict[str, Any]] = {}

    for group in groups:
        for row in group:
            resource_id = str(row.get("resource_id") or "").strip()
            if not resource_id:
                continue

            previous = best_by_resource.get(resource_id)
            if previous is None or int(row.get("_score", 0)) > int(previous.get("_score", 0)):
                best_by_resource[resource_id] = dict(row)

    merged = sorted(
        best_by_resource.values(),
        key=lambda row: (-int(row.get("_score", 0)), str(row.get("resource_id") or "")),
    )

    results: List[Dict[str, Any]] = []
    for row in merged[:limit]:
        cleaned = dict(row)
        cleaned.pop("_score", None)
        results.append(cleaned)
    return results


@router.post("/player-tags")
def upsert_player_tag(payload: PlayerTagUpsertRequest):
    player_id = str(payload.player_id or payload.player or "").strip()
    resource_id = str(payload.resource_id or payload.resource or "").strip()
    tag = str(payload.tag or "").strip()

    if not player_id or not tag or not resource_id:
        raise HTTPException(status_code=400, detail="player/tag/resource are required")

    item = player_tag_store.upsert_tag(
        player_id=player_id,
        tag=tag,
        resource_id=resource_id,
        resource_type=payload.resource_type,
        namespace=payload.namespace,
        source=payload.source,
    )
    if item is None:
        raise HTTPException(status_code=400, detail="invalid player tag payload")

    return {
        "status": "ok",
        "item": item,
    }


@router.get("/player-tags/{player_id}")
def list_player_tags(player_id: str):
    items = player_tag_store.list_player_tags(player_id)
    return {
        "status": "ok",
        "player": str(player_id or "").strip(),
        "tags": _group_player_tags(items),
        "items": items,
    }


@router.delete("/player-tags")
def delete_player_tag_binding(payload: PlayerTagDeleteRequest):
    if payload.id is not None:
        return {
            "status": "ok",
            "deleted": player_tag_store.delete_tag(payload.id),
        }

    player_id = str(payload.player_id or payload.player or "").strip()
    tag = str(payload.tag or "").strip()
    if not player_id or not tag:
        raise HTTPException(status_code=400, detail="id or player/tag is required")

    return {
        "status": "ok",
        "deleted": player_tag_store.delete_player_tag(player_id=player_id, tag=tag),
    }


@router.delete("/player-tags/{tag_id}")
def delete_player_tag(tag_id: int):
    return {
        "status": "ok",
        "deleted": player_tag_store.delete_tag(tag_id),
    }


@router.get("/resources/search")
def search_resources(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(default="all"),
):
    raw_query = str(q or "").strip()
    normalized_query = _normalize_token(raw_query)
    if not normalized_query:
        return {
            "status": "ok",
            "query": raw_query,
            "items": [],
        }

    source_mode = _normalize_source_mode(source)
    local_items: List[Dict[str, Any]] = []
    proxy_items: List[Dict[str, Any]] = []

    if source_mode in {"all", "registry"}:
        local_items = _search_local_registry(normalized_query, limit)

    if source_mode in {"all", "proxy"}:
        proxy_items = _search_proxy_registry(normalized_query, limit)

    items = _merge_search_results(local_items, proxy_items, limit=limit)

    return {
        "status": "ok",
        "query": raw_query,
        "items": items,
    }

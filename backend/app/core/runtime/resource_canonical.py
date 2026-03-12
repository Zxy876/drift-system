from __future__ import annotations

from typing import Any


_DIRECT_RESOURCE_ALIASES = {
    "porkchop": "pork",
    "raw_porkchop": "pork",
    "cooked_porkchop": "pork",
}


def _strip_collect_prefix(token: str) -> str:
    if token.startswith("collect_"):
        return token[len("collect_") :]
    if token.startswith("collect:"):
        return token[len("collect:") :]
    return token


def _strip_namespace_or_suffix(token: str) -> str:
    if ":" not in token:
        return token

    head, tail = token.split(":", 1)
    if head in {"minecraft", "mc"}:
        if ":" in tail:
            tail = tail.split(":", 1)[0]
        return tail

    return head


def normalize_inventory_resource_token(raw_value: Any) -> str:
    token = str(raw_value or "").strip().lower()
    if not token:
        return ""

    token = token.replace("-", "_").replace(" ", "_")
    token = _strip_collect_prefix(token)
    token = _strip_namespace_or_suffix(token)
    token = token.strip("_")
    if not token:
        return ""

    aliased = _DIRECT_RESOURCE_ALIASES.get(token)
    if aliased:
        return aliased

    if token.endswith("_log") or token.endswith("_wood") or token.endswith("_stem"):
        return "wood"

    return token
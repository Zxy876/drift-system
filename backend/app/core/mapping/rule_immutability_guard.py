from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_rule_version_hashes(registry: dict[str, dict[str, dict[str, Any]]]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for rule_version in sorted(registry.keys()):
        rules = registry.get(rule_version)
        if not isinstance(rules, dict):
            hashes[rule_version] = _stable_hash({})
            continue
        hashes[rule_version] = _stable_hash(rules)
    return hashes


def compute_registry_digest(rule_hashes: dict[str, str]) -> str:
    ordered = [{"rule_version": version, "hash": rule_hashes[version]} for version in sorted(rule_hashes.keys())]
    return _stable_hash(ordered)


def evaluate_rule_immutability(
    *,
    default_rule_version: str,
    registry: dict[str, dict[str, dict[str, Any]]],
    freeze_snapshot: dict[str, Any],
) -> dict:
    if not isinstance(registry, dict):
        return {
            "status": "FAIL",
            "failure_codes": ["INVALID_REGISTRY"],
            "details": {"reason": "registry must be dict"},
        }

    if not isinstance(freeze_snapshot, dict):
        return {
            "status": "FAIL",
            "failure_codes": ["INVALID_FREEZE_SNAPSHOT"],
            "details": {"reason": "freeze_snapshot must be dict"},
        }

    frozen_default_rule_version = str(freeze_snapshot.get("frozen_default_rule_version") or "").strip()
    frozen_rule_hashes_raw = freeze_snapshot.get("frozen_rule_hashes")
    frozen_registry_digest = str(freeze_snapshot.get("frozen_registry_digest") or "").strip()

    if not isinstance(frozen_rule_hashes_raw, dict):
        return {
            "status": "FAIL",
            "failure_codes": ["INVALID_FREEZE_SNAPSHOT"],
            "details": {"reason": "frozen_rule_hashes must be dict"},
        }

    frozen_rule_hashes = {
        str(version): str(hash_value)
        for version, hash_value in frozen_rule_hashes_raw.items()
        if isinstance(version, str) and isinstance(hash_value, str)
    }

    current_default_rule_version = str(default_rule_version or "").strip()
    current_rule_hashes = compute_rule_version_hashes(registry)
    current_registry_digest = compute_registry_digest(current_rule_hashes)

    failure_codes: list[str] = []
    issues: list[dict[str, Any]] = []

    if not current_default_rule_version:
        failure_codes.append("DEFAULT_RULE_VERSION_MISSING")
        issues.append({"code": "DEFAULT_RULE_VERSION_MISSING", "reason": "default rule version is empty"})
    elif current_default_rule_version not in registry:
        failure_codes.append("DEFAULT_RULE_VERSION_NOT_FOUND")
        issues.append({
            "code": "DEFAULT_RULE_VERSION_NOT_FOUND",
            "default_rule_version": current_default_rule_version,
        })

    for frozen_version, expected_hash in sorted(frozen_rule_hashes.items()):
        actual_hash = current_rule_hashes.get(frozen_version)
        if actual_hash is None:
            failure_codes.append("FROZEN_RULE_VERSION_MISSING")
            issues.append({
                "code": "FROZEN_RULE_VERSION_MISSING",
                "rule_version": frozen_version,
            })
            continue

        if actual_hash != expected_hash:
            failure_codes.append("FROZEN_RULE_MUTATED")
            issues.append({
                "code": "FROZEN_RULE_MUTATED",
                "rule_version": frozen_version,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            })

    if (
        frozen_default_rule_version
        and current_default_rule_version == frozen_default_rule_version
        and frozen_registry_digest
        and current_registry_digest != frozen_registry_digest
    ):
        failure_codes.append("RULE_VERSION_NOT_BUMPED")
        issues.append({
            "code": "RULE_VERSION_NOT_BUMPED",
            "frozen_default_rule_version": frozen_default_rule_version,
            "current_default_rule_version": current_default_rule_version,
            "frozen_registry_digest": frozen_registry_digest,
            "current_registry_digest": current_registry_digest,
        })

    dedup_failure_codes = sorted(set(failure_codes))
    status = "PASS" if not dedup_failure_codes else "FAIL"

    return {
        "status": status,
        "failure_codes": dedup_failure_codes,
        "details": {
            "frozen_default_rule_version": frozen_default_rule_version,
            "current_default_rule_version": current_default_rule_version,
            "frozen_registry_digest": frozen_registry_digest,
            "current_registry_digest": current_registry_digest,
            "frozen_rule_hashes": frozen_rule_hashes,
            "current_rule_hashes": current_rule_hashes,
            "issues": issues,
        },
    }

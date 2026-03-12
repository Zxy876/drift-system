#!/usr/bin/env python3
"""Utility to validate and normalize heart level JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND_ROOT = Path(__file__).resolve().parent.parent
LEVEL_DIR = BACKEND_ROOT / "data" / "flagship_levels"


class ValidationError(Exception):
    """Raised when strict validation fails."""


def coerce_text(source: Dict[str, Any]) -> List[str]:
    raw_text = source.get("text")
    if isinstance(raw_text, list):
        return list(raw_text)
    if isinstance(raw_text, str):
        text = raw_text.strip()
        return [text] if text else []
    return []


def ensure(condition: bool, description: str, strict: bool, fixer) -> Tuple[bool, List[str], List[str]]:
    fixes: List[str] = []
    problems: List[str] = []
    changed = False
    if condition:
        return changed, problems, fixes

    if strict:
        problems.append(description)
        return changed, problems, fixes

    fixer()
    changed = True
    fixes.append(description)
    return changed, problems, fixes


def validate_file(path: Path, strict: bool) -> Tuple[bool, List[str]]:
    with path.open("r", encoding="utf-8") as fp:
        data: Dict[str, Any] = json.load(fp)

    expected_id = path.stem
    problems: List[str] = []
    fixes: List[str] = []
    changed = False

    def record(result: Tuple[bool, List[str], List[str]]) -> None:
        nonlocal changed, problems, fixes
        upd_changed, upd_problems, upd_fixes = result
        if upd_changed:
            changed = True
        if upd_problems:
            problems.extend(upd_problems)
        if upd_fixes:
            fixes.extend(upd_fixes)

    record(ensure(data.get("id") == expected_id,
                  f"id mismatch (expected '{expected_id}')",
                  strict,
                  lambda: data.__setitem__("id", expected_id)))

    # Ensure narrative structure
    def build_narrative() -> None:
        data["narrative"] = {"text": coerce_text(data)}

    record(ensure(isinstance(data.get("narrative"), dict),
                  "narrative must be an object",
                  strict,
                  build_narrative))

    if isinstance(data.get("narrative"), dict):
        narrative = data["narrative"]

        def fix_text_list() -> None:
            narrative["text"] = coerce_text({"text": narrative.get("text")})

        record(ensure(isinstance(narrative.get("text"), list),
                      "narrative.text must be a list",
                      strict,
                      fix_text_list))
    else:
        narrative = {}

    # Ensure world patch skeleton stays consistent for downstream consumers
    def fix_world_patch() -> None:
        world_patch = data.get("world_patch")
        if not isinstance(world_patch, dict):
            world_patch = {}
        mc_patch = world_patch.get("mc")
        if not isinstance(mc_patch, dict):
            mc_patch = {}
        variables_patch = world_patch.get("variables")
        if not isinstance(variables_patch, dict):
            variables_patch = {}
        world_patch["mc"] = mc_patch
        world_patch["variables"] = variables_patch
        data["world_patch"] = world_patch

    record(ensure(isinstance(data.get("world_patch"), dict)
                  and isinstance(data.get("world_patch", {}).get("mc"), dict)
                  and isinstance(data.get("world_patch", {}).get("variables"), dict),
                  "world_patch must define 'mc' and 'variables' objects",
                  strict,
                  fix_world_patch))

    # Ensure scene is an object
    record(ensure(isinstance(data.get("scene"), dict),
                  "scene must be an object",
                  strict,
                  lambda: data.__setitem__("scene", {})))

    # Ensure tasks is a list
    def fix_tasks() -> None:
        data["tasks"] = list(data.get("tasks") or [])

    record(ensure(isinstance(data.get("tasks"), list),
                  "tasks must be a list",
                  strict,
                  fix_tasks))

    if strict and problems:
        return changed, problems

    if not strict and changed:
        with path.open("w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.write("\n")

    # When not strict we log fixes for visibility
    if fixes and not strict:
        for fix in fixes:
            print(f"[updated] {path.name}: {fix}")

    return changed, problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally normalize heart level files.")
    parser.add_argument("--strict", action="store_true", help="Only validate; exit with failure if fixes are needed.")
    args = parser.parse_args()

    if not LEVEL_DIR.exists():
        print(f"[validate_levels] directory not found: {LEVEL_DIR}", file=sys.stderr)
        return 1

    overall_problems: List[str] = []
    changed_count = 0

    for path in sorted(LEVEL_DIR.glob("*.json")):
        changed, problems = validate_file(path, args.strict)
        if changed:
            changed_count += 1
        if problems:
            overall_problems.append(f"{path.name}: " + "; ".join(problems))

    if overall_problems:
        print("[validate_levels] issues detected:")
        for item in overall_problems:
            print(f"  - {item}")
        return 1

    if args.strict:
        print("[validate_levels] all files passed strict validation")
    else:
        print(f"[validate_levels] validation complete. Files updated: {changed_count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-${1:-https://drift-backend-production-c2a5.up.railway.app}}"
PLAYER_ID="${PLAYER_ID:-${2:-mc_smoke_$(date +%s)}}"
TAG="${TAG:-shrine}"
RESOURCE_ID="${RESOURCE_ID:-minecraft:lantern}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-20}"
CURL_RETRY="${CURL_RETRY:-5}"
CURL_RETRY_DELAY="${CURL_RETRY_DELAY:-1}"

CURL_COMMON_OPTS=(
  --retry "${CURL_RETRY}"
  --retry-all-errors
  --retry-delay "${CURL_RETRY_DELAY}"
  --connect-timeout 10
  --max-time 30
)

TMP_DIR="${TMP_DIR:-/tmp}"
UPSERT_JSON="${TMP_DIR}/drift_mc_test_upsert.json"
SPAWN_JSON="${TMP_DIR}/drift_mc_test_spawn.json"
BEST_JSON="${TMP_DIR}/drift_mc_test_best.json"

echo "[1/3] upsert registry mapping"
echo "BASE_URL=${BASE_URL}"
echo "PLAYER_ID=${PLAYER_ID}"
echo "TAG=${TAG}"
echo "RESOURCE_ID=${RESOURCE_ID}"

curl -sS "${CURL_COMMON_OPTS[@]}" -X POST "${BASE_URL}/registry/player-tags" \
  -H 'Content-Type: application/json' \
  -d "{\"player\":\"${PLAYER_ID}\",\"tag\":\"${TAG}\",\"resource\":\"${RESOURCE_ID}\"}" \
  > "${UPSERT_JSON}"

echo "[2/3] trigger spawnfragment with deterministic-seed variation"
ATTEMPT=1
ALLOWED=0
EVENT_COUNT=0
HAS_PATCH=0
BEST_ALLOWED=0

while [ "${ATTEMPT}" -le "${MAX_ATTEMPTS}" ]; do
  HINT="${TAG}_${ATTEMPT}"

  curl -sS "${CURL_COMMON_OPTS[@]}" -X POST "${BASE_URL}/world/story/${PLAYER_ID}/spawnfragment" \
    -H 'Content-Type: application/json' \
    -d "{\"scene_hint\":\"${HINT}\"}" \
    > "${SPAWN_JSON}"

  STATUS_LINE=$(python3 - <<PY
import json
from pathlib import Path
s = json.loads(Path("${SPAWN_JSON}").read_text())
g = s.get("generation_policy_gate") or {}
scene = s.get("scene") if isinstance(s.get("scene"), dict) else {}
event_count = int(s.get("event_count") or scene.get("event_count") or 0)
patch = s.get("world_patch") if isinstance(s.get("world_patch"), dict) else {}
has_patch = bool(patch)
print(f"allowed={bool(g.get('allowed'))} reason={g.get('reason')} event_count={event_count} has_patch={has_patch}")
PY
)
  echo "attempt ${ATTEMPT}: ${STATUS_LINE}"

  read -r ALLOWED EVENT_COUNT HAS_PATCH <<<"$(python3 - <<PY
import json
from pathlib import Path
s = json.loads(Path("${SPAWN_JSON}").read_text())
allowed = 1 if bool((s.get("generation_policy_gate") or {}).get("allowed")) else 0
scene = s.get("scene") if isinstance(s.get("scene"), dict) else {}
event_count = int(s.get("event_count") or scene.get("event_count") or 0)
patch = s.get("world_patch") if isinstance(s.get("world_patch"), dict) else {}
has_patch = 1 if bool(patch) else 0
print(f"{allowed} {event_count} {has_patch}")
PY
 )"

  if [ "${ALLOWED}" = "1" ] && [ "${EVENT_COUNT}" -gt 0 ] && [ "${HAS_PATCH}" = "1" ]; then
    cp "${SPAWN_JSON}" "${BEST_JSON}"
    BEST_ALLOWED=1
    break
  fi

  if [ "${ALLOWED}" = "1" ] && [ "${BEST_ALLOWED}" = "0" ]; then
    cp "${SPAWN_JSON}" "${BEST_JSON}"
    BEST_ALLOWED=1
  fi

  ATTEMPT=$((ATTEMPT + 1))
done

if [ -f "${BEST_JSON}" ]; then
  cp "${BEST_JSON}" "${SPAWN_JSON}"
fi

echo "[3/3] verify pipeline evidence"
python3 - <<PY
import json
import sys
from pathlib import Path

s = json.loads(Path("${SPAWN_JSON}").read_text())

resource_id = "${RESOURCE_ID}"
expected_tag = "${TAG}"

gate = s.get("generation_policy_gate") or {}
scene = s.get("scene") if isinstance(s.get("scene"), dict) else {}
scene_inv = (scene.get("inventory_state") or {}).get("resources") if isinstance(scene, dict) else {}
patch = s.get("world_patch") if isinstance(s.get("world_patch"), dict) else {}
meta = patch.get("meta") if isinstance(patch.get("meta"), dict) else {}

checks = {
    "gate_allowed": bool(gate.get("allowed")),
  "event_count_gt_zero": int(s.get("event_count") or 0) > 0,
  "world_patch_non_empty": bool(patch),
    "top_registry_has_resource": isinstance(s.get("registry_resources"), dict) and resource_id in s.get("registry_resources"),
    "top_registry_match_tag": s.get("registry_match_tag") == expected_tag,
    "scene_inventory_has_resource": isinstance(scene_inv, dict) and resource_id in scene_inv,
    "patch_meta_has_resource": isinstance(meta.get("registry_resources"), dict) and resource_id in meta.get("registry_resources"),
    "patch_meta_match_tag": meta.get("registry_match_tag") == expected_tag,
    "patch_type_spawnfragment": patch.get("type") == "spawnfragment",
}

print("Verification summary:")
for k, v in checks.items():
    print(f"- {k}: {v}")

print("\nSnapshot:")
print("- generation_policy_gate:", gate)
print("- registry_resources(top):", s.get("registry_resources"))
print("- registry_match_tag(top):", s.get("registry_match_tag"))
print("- event_count:", s.get("event_count"))
print("- scene.inventory_state.resources:", scene_inv)
print("- world_patch.keys:", list(patch.keys()))
print("- world_patch.meta:", meta)

if not all(checks.values()):
    print("\nRESULT: FAIL")
    sys.exit(1)

print("\nRESULT: PASS")
PY

#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://drift-backend-production-c2a5.up.railway.app}"
PLAYER_ID="${2:-railway-smoke}"

echo "== health =="
curl -sS -X GET "${BASE_URL}/health" | python3 -m json.tool

echo "== POST /ai/intent =="
curl -sS -X POST "${BASE_URL}/ai/intent" \
  -H 'Content-Type: application/json' \
  -d "{\"player_id\":\"${PLAYER_ID}\",\"text\":\"我想和商人交易\",\"world_state\":{}}" | python3 -m json.tool

echo "== POST /world/apply =="
curl -sS -X POST "${BASE_URL}/world/apply" \
  -H 'Content-Type: application/json' \
  -d "{\"player_id\":\"${PLAYER_ID}\",\"action\":{\"say\":\"继续\"},\"world_state\":{}}" | python3 -m json.tool

echo "== POST /story/load =="
curl -sS -X POST "${BASE_URL}/story/load" \
  -H 'Content-Type: application/json' \
  -d "{\"player_id\":\"${PLAYER_ID}\",\"level_id\":\"flagship_03\"}" | python3 -m json.tool

echo "== POST /story/advance =="
curl -sS -X POST "${BASE_URL}/story/advance" \
  -H 'Content-Type: application/json' \
  -d "{\"player_id\":\"${PLAYER_ID}\",\"world_state\":{},\"action\":{\"say\":\"继续\"}}" | python3 -m json.tool

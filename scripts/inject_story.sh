#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
PLAYER="${PLAYER:-vivn}"
FILE="${1:-}"

if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "Usage: PLAYER=vivn BASE=http://127.0.0.1:8000 $0 path/to/story.txt" >&2
  exit 1
fi

BASE_ENV="$BASE" PLAYER_ENV="$PLAYER" FILE_ENV="$FILE" python3 - <<'PY'
import json
import os
import urllib.request
import urllib.error

base = os.environ["BASE_ENV"]
player = os.environ["PLAYER_ENV"]
file_path = os.environ["FILE_ENV"]

text = open(file_path, "r", encoding="utf-8").read()
payload = {
    "player_id": player,
    "level_id": f"flagship_story_{player}",
    "title": "HTTP 导入剧情",
    "text": text,
}

data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
req = urllib.request.Request(
    base + "/story/inject",
    data=data,
    headers={"Content-Type": "application/json"},
)

try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", "ignore")
        print(body[:4000])
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", "ignore")
    print(f"HTTP {exc.code}")
    print(body[:4000])
    raise SystemExit(1)
PY

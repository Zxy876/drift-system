#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
PLAYER="${PLAYER:-vivn}"
MODE="summary"
RECENT=0

usage() {
  cat <<'EOF'
Usage:
  PLAYER=vivn BASE=http://127.0.0.1:8000 ./scripts/check_apply_report.sh [--json] [--recent N]

Options:
  --json       Output raw last_apply_report JSON only
  --recent N   Output top N recent_apply_reports (build_id/status/failure_code)
  -h, --help   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      MODE="json"
      shift
      ;;
    --recent)
      RECENT="${2:-}"
      if [[ -z "$RECENT" || ! "$RECENT" =~ ^[0-9]+$ ]]; then
        echo "[check_apply_report] --recent requires integer N" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[check_apply_report] Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

URL="${BASE%/}/world/story/${PLAYER}/debug/tasks"
RAW="$(curl -fsS "$URL")"

if command -v python3 >/dev/null 2>&1; then
  if [[ "$MODE" == "json" ]]; then
    RAW_DATA="$RAW" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RAW_DATA", "")
try:
    body = json.loads(raw)
except Exception as exc:
    print(f"[check_apply_report] invalid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

report = body.get("last_apply_report")
if not report:
    print("[check_apply_report] last_apply_report not found", file=sys.stderr)
    sys.exit(2)

print(json.dumps(report, ensure_ascii=False, indent=2))
PY
  else
    RAW_DATA="$RAW" RECENT_N="$RECENT" python3 - <<'PY'
import json
import os
import sys

raw = os.environ.get("RAW_DATA", "")
recent_n = int(os.environ.get("RECENT_N", "0") or "0")

try:
    body = json.loads(raw)
except Exception as exc:
    print(f"[check_apply_report] invalid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

report = body.get("last_apply_report")
if not report:
    print("[check_apply_report] last_apply_report not found", file=sys.stderr)
    sys.exit(2)

fields = [
    ("build_id", report.get("build_id")),
    ("last_status", report.get("last_status")),
    ("last_failure_code", report.get("last_failure_code")),
    ("last_executed", report.get("last_executed")),
    ("last_failed", report.get("last_failed")),
    ("last_duration_ms", report.get("last_duration_ms")),
    ("last_payload_hash", report.get("last_payload_hash")),
    ("report_count", report.get("report_count")),
    ("received_at", report.get("received_at")),
]

for k, v in fields:
    print(f"{k}={v}")

if recent_n > 0:
    print(f"recent_top_{recent_n}:")
    recent = body.get("recent_apply_reports") or []
    for idx, item in enumerate(recent[:recent_n], start=1):
        print(
            f"{idx}. build_id={item.get('build_id')} "
            f"last_status={item.get('last_status')} "
            f"last_failure_code={item.get('last_failure_code')}"
        )
PY
  fi
  exit $?
fi

# fallback: no python3 available
LAST_LINE="$(printf '%s' "$RAW" | tr -d '\n' | sed -n 's/.*"last_apply_report"[[:space:]]*:[[:space:]]*\({[^}]*}\).*/\1/p')"
if [[ -z "$LAST_LINE" || "$LAST_LINE" == "null" ]]; then
  echo "[check_apply_report] last_apply_report not found" >&2
  exit 2
fi

if [[ "$MODE" == "json" ]]; then
  printf '%s\n' "$LAST_LINE"
  exit 0
fi

echo "[check_apply_report] python3 not found, using simplified parser"
for key in build_id last_status last_failure_code last_executed last_failed last_duration_ms last_payload_hash report_count received_at; do
  value="$(printf '%s' "$LAST_LINE" | sed -n "s/.*\"$key\"[[:space:]]*:[[:space:]]*\"\{0,1\}\([^\",}]*\).*/\1/p")"
  echo "$key=${value:-unknown}"
done

if [[ "$RECENT" -gt 0 ]]; then
  echo "recent_top_${RECENT}: unsupported without python3"
fi

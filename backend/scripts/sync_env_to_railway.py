#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

LOCAL_ENV = Path("/Users/zxydediannao/DriftSystem/backend/.env")
SERVICE = "drift-backend"

if not LOCAL_ENV.exists():
    raise SystemExit(f"local env missing: {LOCAL_ENV}")

local = {}
for line in LOCAL_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
    raw = line.strip()
    if not raw or raw.startswith("#") or "=" not in raw:
        continue
    key, value = raw.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if key:
        local[key] = value

recommended_defaults = {
    "PAYLOAD_VERSION": "v2",
    "STORY_ENGINE_MODE": "semantic",
    "DRIFT_ENV": "production",
}

for key, value in recommended_defaults.items():
    local.setdefault(key, value)

subprocess.run(["railway", "service", SERVICE], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
remote_raw = subprocess.check_output(["railway", "variables", "--service", SERVICE, "--json"], text=True)
remote = json.loads(remote_raw)
if not isinstance(remote, dict):
    raise SystemExit("unexpected railway variables JSON format")

updates = {}
for key, value in local.items():
    if value is None:
        continue
    if remote.get(key) != value:
        updates[key] = value

if updates:
    cmd = ["railway", "variables", "--service", SERVICE, "--skip-deploys"]
    for key, value in updates.items():
        cmd.extend(["--set", f"{key}={value}"])
    subprocess.run(cmd, check=True)

print("local_key_count=", len(local))
print("update_count=", len(updates))
print("keys_checked=")
for key in sorted(local.keys()):
    print(" -", key)
if updates:
    print("keys_updated=")
    for key in sorted(updates.keys()):
        print(" -", key)
else:
    print("keys_updated=none")

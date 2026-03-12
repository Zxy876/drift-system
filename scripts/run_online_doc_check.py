import json
import time
import requests

BASE = "https://driftsystem-production-6558.up.railway.app"
PLAYER = "railway_validator"
TITLE = "railway payload_v1 verify"
TEXT = "平静夜晚的湖边，有一座7x5木屋，门朝南，开两扇窗"
LEVEL_IDS = [
    "railway_payload_v1_verify_A1",
    "railway_payload_v1_verify_A2",
    "railway_payload_v1_verify_A3",
]

runs = []
for i, level_id in enumerate(LEVEL_IDS, start=1):
    payload = {
        "level_id": level_id,
        "title": TITLE,
        "text": TEXT,
        "player_id": PLAYER,
    }
    resp = requests.post(BASE + "/story/inject", json=payload, timeout=90)
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text[:500]}

    runs.append(
        {
            "run": i,
            "level_id": level_id,
            "http_status": resp.status_code,
            "content_type": resp.headers.get("Content-Type"),
            "version": data.get("version") if isinstance(data, dict) else None,
            "build_id": data.get("build_id") if isinstance(data, dict) else None,
            "merged_hash": (
                (data.get("hash") or {}).get("merged_blocks")
                if isinstance(data, dict) and isinstance(data.get("hash"), dict)
                else None
            ),
            "commands_len": (
                len(data.get("commands") or [])
                if isinstance(data, dict) and isinstance(data.get("commands"), list)
                else 0
            ),
            "has_world_preview": ("world_preview" in data) if isinstance(data, dict) else False,
        }
    )
    time.sleep(1)

debug_resp = requests.get(BASE + f"/world/story/{PLAYER}/debug/tasks", timeout=60)
try:
    debug_data = debug_resp.json()
except Exception:
    debug_data = {"_raw": debug_resp.text[:500]}

hashes = [item["merged_hash"] for item in runs]
commands = [item["commands_len"] for item in runs]

doc_checks = {
    "version_plugin_payload_v1_3of3": all(r["version"] == "plugin_payload_v1" for r in runs),
    "commands_len_gt_0_3of3": all(r["commands_len"] > 0 for r in runs),
    "merged_hash_equal_3of3": len(set(hashes)) == 1 and None not in hashes,
    "no_world_preview_3of3": all(not r["has_world_preview"] for r in runs),
    "fallback_flag_false": debug_data.get("last_fallback_flag") is False if isinstance(debug_data, dict) else False,
    "fallback_reason_none": debug_data.get("last_fallback_reason") == "none" if isinstance(debug_data, dict) else False,
    "recent_apply_reports_exists": isinstance(debug_data, dict) and ("recent_apply_reports" in debug_data),
    "http_200_3of3": all(r["http_status"] == 200 for r in runs),
}

assessment = {
    "base": BASE,
    "doc_checks": doc_checks,
    "overall_pass_against_doc": all(doc_checks.values()),
    "runs": runs,
    "hashes": hashes,
    "commands": commands,
    "debug": {
        "http_status": debug_resp.status_code,
        "last_fallback_flag": debug_data.get("last_fallback_flag") if isinstance(debug_data, dict) else None,
        "last_fallback_reason": debug_data.get("last_fallback_reason") if isinstance(debug_data, dict) else None,
        "recent_apply_reports_len": (
            len(debug_data.get("recent_apply_reports") or [])
            if isinstance(debug_data, dict) and isinstance(debug_data.get("recent_apply_reports"), list)
            else None
        ),
        "has_recent_apply_reports": ("recent_apply_reports" in debug_data) if isinstance(debug_data, dict) else False,
    },
}

out_path = "/Users/zxydediannao/DriftSystem/docs/online_backend_reason_verification_run.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(assessment, f, ensure_ascii=False, indent=2)

print(json.dumps({
    "overall_pass_against_doc": assessment["overall_pass_against_doc"],
    "doc_checks": doc_checks,
    "hashes": hashes,
    "commands": commands,
    "debug": assessment["debug"],
}, ensure_ascii=False))

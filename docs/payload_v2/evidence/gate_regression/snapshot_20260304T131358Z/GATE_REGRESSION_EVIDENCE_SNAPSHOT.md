# Gate Regression Evidence Snapshot (snapshot_20260304T131358Z)

## Snapshot Intent
- Freeze the latest gate regression evidence after full rerun.
- Keep a timestamped, hash-bound audit package before Phase5 design stage.

## Anchors
- generated_at_utc: `2026-03-04T13:13:58.985041+00:00`
- commit_hash: `d8070014ebeecf03ace9d5541b2783ae10fa58f1`
- snapshot_id: `snapshot_20260304T131358Z`

## Baseline Regression
- command: `python3 -m pytest -q tests/test_phase4_world_patch_module_d.py tests/test_phase4_resource_mapping_module_b.py tests/test_phase4_npc_state_module_a.py tests/test_phase4_event_runtime_module_c.py tests/test_trng_transaction_shell.py`
- return_code: `0`
- output: `phase4_baseline_test_output.txt`

## Gate Results
- gate2_replay_report.json: PASS
- gate2b_execution_replay_report.json: PASS
- gate3_hash_consistency_report.json: PASS
- gate4_strict_integrity_report.json: PASS
- gate5_compatibility_rejection_report.json: PASS
- gate6_rule_immutability_report.json: PASS
- gate7_rollback_safety_report.json: PASS

## Overall
- overall_pass: `true`

## Included Files
- `phase4_baseline_test_output.txt`
- `gate2_replay_report.json`
- `gate2b_execution_replay_report.json`
- `gate3_hash_consistency_report.json`
- `gate4_strict_integrity_report.json`
- `gate5_compatibility_rejection_report.json`
- `gate6_rule_immutability_report.json`
- `gate7_rollback_safety_report.json`
- `artifact_manifest.json`

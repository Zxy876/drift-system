# Phase 4 Gate Regression Commands

## Purpose
- Re-run governance gates after Phase4 closure.
- Confirm Phase3 safety boundaries (Gate5/6/7) remain intact.
- Keep runtime deterministic guarantees auditable.

## Prerequisites
- Run from repository root: `/Users/zxydediannao/DriftSystem`
- Python: `python3`
- Optional: clean working tree before snapshotting evidence.

## Command Set (Recommended Order)

### 0) Phase4 focused runtime regression (closure baseline)
```bash
python3 -m pytest -q \
  tests/test_phase4_world_patch_module_d.py \
  tests/test_phase4_resource_mapping_module_b.py \
  tests/test_phase4_npc_state_module_a.py \
  tests/test_phase4_event_runtime_module_c.py \
  tests/test_trng_transaction_shell.py
```
Expected:
- `21 passed`

### 1) Gate5 compatibility rejection
```bash
python3 tools/gate5_compatibility_rejection_check.py
```
Expected:
- `overall_pass: true`
- Output: `docs/payload_v2/evidence/gate5_compatibility_rejection_report.json`

### 2) Gate6 rule immutability
```bash
python3 tools/gate6_rule_immutability_check.py
```
Expected:
- `overall_pass: true`
- Output: `docs/payload_v2/evidence/gate6_rule_immutability_report.json`

### 3) Gate7 rollback safety
```bash
python3 tools/gate7_rollback_safety_check.py
```
Expected:
- `overall_pass: true`
- Output: `docs/payload_v2/evidence/gate7_rollback_safety_report.json`

## Optional Full Governance Sweep

### Gate2A replay determinism
```bash
./run/gate2_replay_test.sh
```

### Gate2B execution replay determinism
```bash
./run/gate2b_execution_replay_test.sh
```

### Gate6 wrapper
```bash
./run/gate6_rule_immutability_test.sh
```

### Gate7 wrapper
```bash
./run/gate7_rollback_safety_test.sh
```

## Phase4 Snapshot Refresh
```bash
python3 tools/phase4_closure_snapshot.py
```
Expected outputs:
- `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/test_output.txt`
- `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/artifact_manifest.json`
- `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/PHASE4_EVIDENCE_SNAPSHOT.md`

## Go / No-Go
- Go:
  - Phase4 focused runtime regression PASS
  - Gate5 PASS
  - Gate6 PASS
  - Gate7 PASS
- No-Go:
  - Any one command fails or any `overall_pass: false`

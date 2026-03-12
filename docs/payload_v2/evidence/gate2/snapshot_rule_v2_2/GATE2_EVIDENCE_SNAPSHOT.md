# Gate 2 Evidence Snapshot v2.2

## Snapshot Intent
- Freeze Gate 2 evidence at a specific repository state.
- Preserve auditability for future re-validation.

## Scope Status
- Gate 2A (Projection Determinism): PASS
- Gate 2B (Execution Determinism, block + npc_placeholder): PASS
- Real summon replay_v2 coverage: NOT INCLUDED
- Overall Gate 2 status: PARTIAL_PASS

## Environment Anchors
- commit_hash: `54ee783520c301c4626f0b72fc517ee5ca5ff4b1`
- rule_version: `rule_v2_2`
- engine_version: `engine_v2_1`
- schema_version (execution path used in Gate 2B): `plugin_payload_v1`
- schema_version (prepared draft, not executed in Gate 2B): `plugin_payload_v2`

## Evidence Artifacts

| Artifact | SHA256 | Bytes |
|---|---|---:|
| `docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/replay_report.json` | `41e242ab2d82b58a4f1002df5d355c4e8644be533eae547125848cf29e340d16` | 2536 |
| `docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/execution_report.json` | `ee9549f9749a4eac1b86d1590b506a5c8f0fb37f24d17ed7d215f4e908b5a93b` | 2657 |
| `docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/artifact_manifest.json` | *(container manifest for this snapshot)* | *(generated)* |

## Script / Adapter Fingerprints

| File | SHA256 | Bytes |
|---|---|---:|
| `tools/gate2_replay_determinism_check.py` | `a3beadb52f9b10e5b9477ca4ce3c815dc7d630638962983bdc5c451141d4daa5` | 3632 |
| `tools/gate2b_execution_replay_check.py` | `baf8b9074567dddc9c5196f491c110fc67693504dfb44d713077992c4a265827` | 4284 |
| `tools/replay_evidence_adapter.py` | `3cf9313f991edf6cf47e385700d8aa3c3e553578b47c48973e9b447f2aeb0b11` | 1355 |
| `run/gate2_replay_test.sh` | `ec260e78a52e535aae8cdad8517f8fbed9146f5707981016ded856f0859db8de` | 309 |
| `run/gate2b_execution_replay_test.sh` | `edc9deb53781dc376ef10082ab4059109a00d26479b6e77e3abaa6799b5c8665` | 360 |

## Rule/Schema Inputs Fingerprints

| File | SHA256 | Bytes |
|---|---|---:|
| `backend/app/core/mapping/projection_rule_registry.py` | `85f90003215f63bdcc18858b1d2f6ed64114253728049fdfdbab50929dc0ddeb` | 2162 |
| `backend/app/core/executor/plugin_payload_schema_v2.json` | `c2408bf6718d69d3c52dba4fd56bd1de866cc2c56a0f881f3b81dcbbba5cdc0e` | 3943 |

## Execution Commands
- Gate 2A: `PYTEST_CURRENT_TEST=gate2_dry_run ./run/gate2_replay_test.sh`
- Gate 2B: `./run/gate2b_execution_replay_test.sh`

## Audit Notes
- This snapshot certifies determinism for current projection and placeholder execution path only.
- It does not certify replay determinism for real entity summon because executor_v2/replay_v2 summon path is not implemented.

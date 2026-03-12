# Phase 4 Evidence Snapshot v1

## Snapshot Intent
- Freeze Phase4 runtime closure evidence at a deterministic baseline.
- Certify event -> state -> patch chain is complete and replay-stable.

## Closure Status
- Module C: PASS
- Module A: PASS
- Module B: PASS
- Module D: PASS
- Focused regression: 21 passed

## Environment Anchors
- commit_hash: `0bec894aa61ce98eb22af91ed5a72e99385b3c43`
- rule_version: `rule_v2_2`
- engine_version: `engine_v2_1`
- runtime_snapshot: `phase4_runtime_v1`

## Core Artifacts
| Artifact | SHA256 | Bytes |
|---|---|---:|
| `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/test_output.txt` | `a43b1c44dd1e7077494364be64b82b24c56360825914f2412562a9c3c39cbf49` | 99 |
| `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/artifact_manifest.json` | `0496652449e69bbcdeabd28241a28705940684e717e114011cf839b6cf127821` | 2628 |

## Runtime Files
| File | SHA256 | Bytes |
|---|---|---:|
| `backend/app/core/runtime/interaction_event.py` | `0c67c387b00673d8757923df5158c2487b2feff6dfed687f3a80c9a27fbac29b` | 3585 |
| `backend/app/core/runtime/interaction_event_log.py` | `5ae25680b408287c41388d7c35bd08e774520e04809e89df53f5464f7d7c9d8d` | 1326 |
| `backend/app/core/runtime/state_reducer.py` | `e40d95ef2867b9ebbfb417b70c13d9be9379fff03949702097c663a8993d205f` | 9483 |
| `backend/app/core/runtime/npc_state.py` | `65fa6c7abc19fec8cb501553cc63ce6437ee7c824fcd3d99cd970f6583f99c5a` | 3667 |
| `backend/app/core/runtime/resource_mapping.py` | `51fad6515b317d9bfedbf4a0cfaf4bb64962d1340cf4fda751217b2fc07d8f86` | 5482 |
| `backend/app/core/runtime/world_patch.py` | `92c0b06fa5000f1e2370e44508e01831b885c4fda37fd2ad51f3e0bd391cea23` | 8309 |

## Module Tests
| File | SHA256 | Bytes |
|---|---|---:|
| `tests/test_phase4_event_runtime_module_c.py` | `b841965b773a6604274c7d4fafad3b96391d629468f62c5e55bca55ed4c093a9` | 4756 |
| `tests/test_phase4_npc_state_module_a.py` | `a397d2e0c69c8d37ad6ccfda5102a026437efa07246b4d7a40b3451af45232a7` | 4118 |
| `tests/test_phase4_resource_mapping_module_b.py` | `d9423042067a37c8f490db0a8935126c4b7d017f377a09ca22a92a3070484aca` | 4410 |
| `tests/test_phase4_world_patch_module_d.py` | `fb17ec8ddfa5bbb478022349182e0f94bc046acf4ad1bcb91b1d3aa2f8fecc3a` | 6118 |

## Gate Regression Evidence Inputs
| File | SHA256 | Bytes |
|---|---|---:|
| `docs/payload_v2/evidence/gate5_compatibility_rejection_report.json` | `fcb50b2d6bbd18aa3d41c53a4b068beccf65f68723d33baff7686ad51eea6d30` | 804 |
| `docs/payload_v2/evidence/gate6_rule_immutability_report.json` | `1b0bc3ac228b64593df4fa358a23d5a3f7a86b313fccac8548a2ab641a54a269` | 952 |
| `docs/payload_v2/evidence/gate7_rollback_safety_report.json` | `5d4ec930f29ae19698da15d77ca2ce67f13c3ff18c3dade59842cb9eabb37216` | 621 |

## Execution Command
- `python3 -m pytest -q tests/test_phase4_world_patch_module_d.py tests/test_phase4_resource_mapping_module_b.py tests/test_phase4_npc_state_module_a.py tests/test_phase4_event_runtime_module_c.py tests/test_trng_transaction_shell.py`

## Audit Notes
- Phase4 closure certifies deterministic runtime state and deterministic world patch generation.
- No TRNG begin/apply/commit/rollback is included in this snapshot.

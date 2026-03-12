# Compatibility Matrix (Phase 2.2 Freeze)

## Scope
- This document freezes compatibility behavior across client, executor, replay engine, payload version, hash strategy, and rule gates.
- This document is policy-only and does not change runtime wiring.

## Critical Statement
payload_v2 is a strict superset protocol and is not backward compatible with v1 executor.

## 1) Client Version × Payload Version

| Client | payload_v1 | payload_v2 |
|---|---|---|
| v1 client | ✅ Execute | ❌ Reject (`UNSUPPORTED_PAYLOAD_VERSION`) |
| v2 client | ✅ Execute | ✅ Execute |

## 2) Replay Engine Version × Payload Version

| Replay Engine | payload_v1 | payload_v2 |
|---|---|---|
| replay_v1 | ✅ Replay | ❌ Reject (`UNSUPPORTED_REPLAY_VERSION`) |
| replay_v2 | ✅ Replay | ✅ Replay |

## 3) Hash Strategy by Payload Version

| payload_version | hash_scope | hash_field |
|---|---|---|
| v1 | block_ops only | `hash.merged_blocks` |
| v2 | block_ops + entity_ops | `hash.final_commands` |
| v2.1 | block_ops + entity_ops（`commands` 绝对坐标；`block_ops/entity_ops` 为 anchor-relative） | `hash.final_commands` |

## 4) Rule Version Gate

| rule_version | Entity Projection |
|---|---|
| `< rule_v2_2` | ❌ Unsupported |
| `>= rule_v2_2` | ✅ Allowed (subject to engine support) |

## 5) Deterministic Enforcement
- v2 entity command type is constrained to deterministic `summon` subset only.
- Free-form NBT is forbidden.
- Runtime random, tick-driven behavior, pathfinding, scheduler hooks are forbidden for deterministic replay.

## 6) Rejection Contracts
- v1 executor receiving `payload_v2` must fail closed with explicit code: `UNSUPPORTED_PAYLOAD_VERSION`.
- replay_v1 receiving `payload_v2` must fail closed with explicit code: `UNSUPPORTED_REPLAY_VERSION`.
- Unknown `rule_version` must fail closed with explicit code: `RULESET_NOT_FOUND`.

## 7) Migration Strategy (Order Is Mandatory)
1. Upgrade replay engine to `replay_v2`.
2. Upgrade executor/client to `v2` capable path.
3. Enable payload_v2 generation.

## 8) Rollout Gate Checklist
- [ ] replay_v2 supports v1 + v2 dual replay.
- [ ] executor_v2 validates v2 schema and deterministic summon whitelist.
- [ ] hash canonicalization for `final_commands` is frozen and verified.
- [x] explicit rejection codes are observable in logs/trace.
- [ ] canary environment validates no hash drift across repeated builds.

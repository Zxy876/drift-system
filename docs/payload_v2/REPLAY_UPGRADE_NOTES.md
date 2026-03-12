# Replay Upgrade Notes (v1 -> v2)

## Objective
Guarantee replay determinism during transition from block-only payloads to block+entity payloads.

## Version Routing Rules
- If `version=plugin_payload_v1`: use replay_v1 rules (`hash.merged_blocks`).
- If `version=plugin_payload_v2`: use replay_v2 rules (`hash.final_commands`).
- Unknown version: reject with `UNSUPPORTED_REPLAY_VERSION`.

## Replay v2 Requirements
- Support union commands: `setblock` and deterministic `summon`.
- Apply canonical command ordering before hash verification.
- Verify `hash.final_commands` before applying any operation.

## Determinism Rules
- No world-state reads for replay decision.
- No scheduler/tick dependency.
- No probabilistic behavior.
- No free-form entity fields outside schema whitelist.

## Backward Compatibility
- replay_v2 must replay payload_v1 without behavior change.
- replay_v1 does not need to support payload_v2 and must reject clearly.

## Verification Checklist
- [ ] Same payload_v2 replayed N times yields identical world state and identical final hash verification result.
- [ ] payload_v1 replay result unchanged after replay_v2 rollout.
- [ ] reject paths return stable failure codes.
- [ ] cross-version confusion tests are present (`v1 engine + v2 payload` rejects).

## Operational Guidance
- Deploy replay_v2 first.
- Run dual-version replay verification in pre-production.
- Only after replay gate passes, allow executor v2 canary.

# Executor Upgrade Path (Draft, No Runtime Change)

## Goal
Define a safe staged path for introducing payload_v2 execution without production instability.

## Non-goals
- No implementation in this phase.
- No runtime switch in this phase.
- No mixed-mode implicit fallback.

## Stage Plan

### Stage A: Compatibility Preparation
- Add schema loader support for `plugin_payload_schema_v2.json` in executor code path (dark mode only).
- Keep runtime execute path on v1.
- Add explicit reject code for unknown payload version.

### Stage B: Validation-Only Shadow
- Parse and validate payload_v2 in shadow mode.
- Do not execute entity commands.
- Record validation result and canonical hash verification result.

### Stage C: Controlled Execution (Canary)
- Enable v2 execution for a small canary cohort.
- Enforce deterministic summon whitelist:
  - `entity_type=villager`
  - `no_ai=true`
  - `silent=true`
  - fixed `rotation`
  - no free-form NBT
- Compare repeated run hash stability and replay consistency.

### Stage D: Broad Enablement
- Expand cohort after canary SLO gates pass.
- Keep v1 path available for rollback.

## Hard Gates
- Gate 1: replay_v2 must be deployed before any v2 execution.
- Gate 2: hash canonicalization must match `hash.final_commands` exactly.
- Gate 3: explicit failure codes must be emitted for reject scenarios.

## Failure Codes (Recommended)
- `UNSUPPORTED_PAYLOAD_VERSION`
- `INVALID_COMMAND_TYPE`
- `INVALID_ENTITY_COMMAND`
- `FINAL_COMMANDS_HASH_MISMATCH`
- `UNSUPPORTED_REPLAY_VERSION`

## Rollback Strategy
- Disable v2 generation first.
- Keep replay_v2 enabled (must remain backward-compatible with v1).
- Route all new builds to v1 payload path until incident resolved.

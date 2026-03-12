# Phase 5 启动清单（TRNG Transaction Shell Entry Spec）

## 设计评审冻结结论（2026-03-04）
- 评审结论：通过（Design Freeze）。
- 冻结范围：`begin/apply/commit/rollback` API、事务不变量、测试矩阵。
- 前置证据：Gate 回归全量通过并已封存快照：
  - `docs/payload_v2/evidence/gate_regression/snapshot_20260304T164303Z/GATE_REGRESSION_EVIDENCE_SNAPSHOT.md`
  - `docs/payload_v2/evidence/gate_regression/snapshot_20260304T164303Z/artifact_manifest.json`
- 本文档状态：可作为 Phase5 实现前唯一入口规范；实现阶段不得越权扩展范围。

## Scope Statement
- Phase5 目标：在既有 Phase4 runtime 之上增加事务壳层（TRNG shell）。
- Phase5 不重写：event model、state reducer、world patch generator。
- Phase5 本文档仅定义入口规范，不实现代码。

## Entry Baseline (Must Be True)
- Phase4 modules completed: C/A/B/D
- Phase4 closure regression PASS (`21 passed`)
- Gate5 PASS
- Gate6 PASS
- Gate7 PASS
- Evidence snapshot ready:
  - `docs/payload_v2/evidence/phase4/snapshot_runtime_v1/PHASE4_EVIDENCE_SNAPSHOT.md`

## Architecture Contract

### Existing Chain (Frozen)
- `event_log -> state_reducer -> runtime_state -> world_patch_generator`
- Deterministic constraints remain mandatory:
  - `state = f(event_log)`
  - `patch = f(runtime_state, event)`

### Phase5 Added Layer
- Add transaction wrapper around runtime chain:
  - `begin`
  - `apply`
  - `commit`
  - `rollback`

## TRNG Shell API Entry Spec

### begin
Input:
- `committed_graph`
- `committed_state`

Output:
- `tx_context` (draft graph/state handles)

Constraints:
- No committed visibility changes before `commit`.

Freeze Notes:
- 必须返回稳定 `tx_id` 与 `base_state_hash`。
- `tx_context` 只允许持有 draft 句柄，不得暴露 committed 可写引用。

### apply
Input:
- `tx_context`
- `interaction_event`

Output:
- draft updates only (`draft_state`, `draft_patch`, audit trace)

Constraints:
- apply is deterministic for same `(tx_context, event)`.
- failures must be explicit and auditable.

Freeze Notes:
- `apply` 输出必须包含 `draft_state_hash` 与 `world_patch_payload_hash`（可用于后续 commit 校验）。
- `apply` 失败不得污染 committed；必须生成可审计 reject 记录。

### commit
Input:
- `tx_context`

Output:
- new committed graph/state snapshot

Constraints:
- commit must validate invariants before publish.
- publish is atomic at shell boundary.

Freeze Notes:
- commit 收据必须至少包含：`tx_id`、`committed_state_hash`、`committed_graph_hash`、`commit_timestamp`。
- 原子发布粒度固定为 graph/state/version tuple，不允许拆分提交。

### rollback
Input:
- `tx_context`

Output:
- rollback receipt + reason

Constraints:
- committed graph/state remain unchanged.
- rollback is idempotent.

Freeze Notes:
- rollback 收据必须包含 `tx_id`、`rollback_reason`、`base_state_hash`。
- 重复 rollback 的可观察结果必须一致（幂等）。

## Invariants (Phase5 Mandatory)
- I1: Draft isolation
  - draft writes never leak to committed state pre-commit.
- I2: Atomic publish
  - commit publishes graph/state/version tuple atomically.
- I3: Deterministic replay
  - same committed base + same event sequence => same committed result hash.
- I4: Audit completeness
  - each transaction records begin/apply/commit/rollback trace with stable IDs.
- I5: Rule immutability compatibility
  - shell must not mutate frozen rule versions.

## Invariant Freeze Acceptance
- IA-1（Isolation）: 任意 `apply` 之前/之后，committed hash 不变。
- IA-2（Atomicity）: commit 前后只允许 0/1 次状态切换，不允许部分可见。
- IA-3（Determinism）: 同 base + 同事件序列得到同 committed hash。
- IA-4（Audit）: begin/apply/commit/rollback 均产生日志，且可由 `tx_id` 串联。
- IA-5（Immutability）: 事务层不得改写 `rule_version` 冻结内容。

## Data/Hash Binding Requirements
- Transaction audit payload must include:
  - `tx_id`
  - `base_state_hash`
  - `draft_state_hash`
  - `world_patch_payload_hash`
  - `rule_version`
  - `engine_version`
- Commit receipt must include:
  - `committed_state_hash`
  - `committed_graph_hash`
  - `commit_timestamp`

## Phase5 Test Entry Matrix (Definition Only)
- T1: begin/apply isolation test
- T2: commit atomicity test
- T3: rollback safety test
- T4: replay determinism test (transactional)
- T5: invariant violation reject test
- T6: compatibility with existing Gate5/6/7

### Test Freeze Criteria
- T1 通过标准：draft 变更前后 committed hash 一致。
- T2 通过标准：commit 仅一次发布，发布后 graph/state/version 同步可见。
- T3 通过标准：rollback 后 committed 与 begin 前一致，且可重复执行。
- T4 通过标准：相同输入重放得到相同 `committed_state_hash`。
- T5 通过标准：违规事务返回 reject，且无 committed 污染。
- T6 通过标准：不影响既有 Gate5/6/7 通过状态。

## Phase5 实施边界（冻结）
- 允许：新增事务壳层接口与审计结构。
- 禁止：改写 Phase4 reducer 语义、改写 world patch 生成规则、引入非确定性副作用。
- 禁止：在本评审阶段提交 TRNG 运行时代码（本阶段仅规格冻结）。

## 下一步（进入实现前）
- 以本文件为准生成实现任务拆分（仅任务拆分，不编码）。
- 先建立测试骨架（空实现可失败），再进入最小可用实现。
- 实现完成后必须复跑 Gate 回归并追加新快照。

## 执行产物入口（任务拆分 + 测试骨架）
- 任务拆分文档：`docs/payload_v2/PHASE5_TASK_BREAKDOWN.md`
- 测试骨架（Fail-first）：
  - `tests/test_trng_begin.py`
  - `tests/test_trng_apply.py`
  - `tests/test_trng_commit.py`
  - `tests/test_trng_rollback.py`
- 当前状态：上述 4 个骨架已细化为 AAA（Arrange/Act/Assert）模板，保持 fail-first。
- 说明：本阶段仅落地约束与测试入口，不包含 TRNG 事务实现代码。

## Non-Goals for Kickoff
- No direct world mutation API redesign.
- No gameplay feature expansion.
- No Phase4 reducer semantics change.
- No executor protocol migration in kickoff stage.

## Exit Criteria for Phase5 Design Stage
- TRNG shell API reviewed and frozen.
- invariants signed off.
- test matrix approved.
- implementation plan split into milestones (without coding yet).

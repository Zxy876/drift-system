# Phase 3 Sandbox Validation Plan (Minimal)

## 目标
在不接线上 API 的前提下，验证 executor_v2 的最小 deterministic entity 执行闭环。

## 范围（只做最小）
- 仅支持 `summon villager`。
- 固定参数：`no_ai=true`, `silent=true`, `profession=none`, `rotation=90`。
- 禁止自由 NBT、禁止 pathfinding、禁止 scheduler/tick 行为。

## Gate 2 分层说明
- Gate 2A（Projection Determinism）：已完成，证据见 `evidence/gate2_replay_report.json`。
- Gate 2B（Execution Replay Determinism）：当前完成范围为 `block + npc_placeholder`，证据见 `evidence/gate2b_execution_replay_report.json`。
- 注意：真实 `summon` replay 仍未纳入本阶段验证。

## 输入场景集
1. fog-only
2. npc-only (`npc_behavior.lake_guard`)
3. fog+npc
4. npc+unsupported_sound（strict / default 各一）

## 验证项
1. Schema 验证：payload_v2 通过 schema_v2。
2. Canonical Hash：同输入重复 100 次，`hash.final_commands` 完全一致。
3. Replay 一致性：相同 payload 回放结果一致。
4. Strict 拒绝：unsupported entity 语义时 422 + 不落盘 + trace 完整。
5. 兼容拒绝：v1 executor 对 v2 payload 明确拒绝。

## 产物
- `sandbox_hash_report.json`
- `sandbox_replay_report.json`
- `sandbox_reject_report.json`
- `sandbox_compat_report.json`

## 退出准则
- 所有验证项 PASS 后，才允许将 Gate 2/3/4/5 标记为 PASS。

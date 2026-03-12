# Phase 4 启动清单（NPC + Interaction Runtime，TRNG 前）

## 阶段编号对齐（统一口径）
- Phase 3（已完成）：payload_v2 治理与 7 gates 基线。
- Phase 4（本文）：NPC 系统 + 玩家交互事件系统 + 背包资源映射（只读绑定）。
- Phase 5（后续）：TRNG Transaction Shell（begin/apply/commit/rollback 与因果事务化）。

## Phase 4 目标
- 完成 NPC registry 与 NPC state（含关系值）作为互动运行时基础。
- 完成玩家背包资源映射（只读绑定），为场景导入与互动补丁提供资源约束。
- 完成玩家交互事件系统（talk/collect/trigger）到 world patch 的实时路径。
- 保持 payload 链路可审计：determinism、hash、trace 字段持续可验证。
- 将本阶段产物收敛为 TRNG-ready runtime input layer（供 Phase 5 事务化接入复用）。
- Runtime Data Model 全量版本化（schema versioned），为 Phase 5 升级与回放兼容做前置准备。

## 非目标（红线）
- ❌ 不做 TRNG begin/apply/commit/rollback，不引入事务壳层。
- ❌ 不做 TRNG 因果链编排（背包/关系/场景的事务化解释留到 Phase 5）。
- ❌ 不修改 Phase 3 已冻结治理边界（兼容拒绝语义、规则不可变约束、回滚安全语义）。
- ❌ 不将 NPC 行为层扩展为复杂决策系统（仅做运行时接入与状态驱动）。

## 入场前置（当前基线）
- Phase 3 precheck 必须保持 GO，且 7/7 gates 为 PASS。
- Gate 5 / Gate 6 / Gate 7 回归作为本阶段的持续守卫，不得退化。

## 验收门槛（全部必须通过）
1. 导入关卡时仅使用玩家背包资源；缺资源时降级为文字或轻量 patch，并在 trace 输出 missing_resources。
2. NPC 是否进入关卡取决于 npc_relationship_state（阈值），且通过后写入 npc_available=true 并进入背包备案映射。
3. 玩家交互事件（talk/collect/trigger）可实时产生世界变化（走 payload），并保持 determinism 与 hash 可审计。
4. anchor 可由玩家设定：在既有 scene anchor routing 基础上补齐 player set_anchor 的持久化与优先级规则。
5. interaction event log 必须为 append-only 且 immutable，不允许覆盖或改写历史事件。
6. world patch 生成必须满足同输入同输出（identical inputs => identical patch/hash）。
7. state update 必须满足 `state = f(event_log)`，并可从同一 event_log 重建出相同 state_hash。
8. Runtime Data Model（NPCState / ResourceInventory / InteractionEvent / WorldPatch）必须包含 version 字段。
9. 必须提供 `EVENT_REPLAY_TEST`：给定相同 event_log，重建 runtime_state 与 world_patch 的 hash 一致。

## 首批任务拆解（非 TRNG）
1. NPC registry/state
   - 建立 NPC 元数据、关系值状态模型、阈值判定接口。
   - 输出最小审计字段：npc_id、relationship_value、threshold、npc_available、decision。

2. resource mapping（只读绑定）
   - 建立玩家背包到可用资源清单映射。
   - 导入路径接入缺资源降级策略，并在 trace 输出 missing_resources。

3. interaction event log
   - 定义 talk/collect/trigger 事件模型与日志落点。
   - 要求事件 append-only、immutable、可回放、可关联到对应 world patch 与 hash。
   - 定义 event→state 映射规则，确保 state update 为 event_log 的确定性函数。

4. realtime patch apply（非 TRNG）
   - 事件触发后生成并应用 payload patch。
   - 保持 hash 稳定与证据可复放；同输入必须生成同 patch/hash；不引入事务提交语义。
   - patch 审计字段必须包含 input_state_hash 与 payload_hash。

## 设计约束（Phase 4 内）
- NPC 实体链路优先走 payload_v2（entity_ops / summon / replay_v2）。
- 背包资源映射与互动事件可先支持 v1/v2 的只读绑定，但最终落点对齐到 v2。
- TRNG 不属于 payload_v1 能力范畴；Phase 4 只准备“可被事务化”的输入与事件流。
- 事件日志不可变：仅允许 append，不允许 update/delete 历史事件。
- Patch 生成确定性：相同 inventory + npc_state + anchor + event 输入必须得到相同 patch 与 payload_hash。
- 状态更新确定性：相同 event_log 必须得到相同 runtime_state 与 state_hash。

## Runtime Data Model（Phase 4）

### NPCState
- version
- npc_id
- relationship_value
- threshold
- npc_available
- anchor

### ResourceInventory
- version
- player_id
- resources[]
- timestamp

### InteractionEvent
- version
- event_id
- type（talk | collect | trigger）
- player_id
- npc_id
- anchor
- timestamp

### WorldPatch
- version
- patch_id
- source_event
- input_state_hash
- payload_hash
- anchor
- timestamp

## Anchor Resolution Order
1. player explicit anchor（玩家显式 set_anchor）
2. scene anchor routing
3. npc anchor
4. default home anchor

## 状态重建规则
- runtime_state 更新必须由 event_log 纯函数决定：`runtime_state = reduce(event_log, initial_state)`。
- 在相同 initial_state 与相同 event_log 下，state_hash 必须一致。
- world_patch 必须绑定 source_event + input_state_hash，用于重放与审计追踪。

## Runtime 定位
- Phase 4 = world runtime layer（玩家行为 → 事件 → 状态更新 → 世界变化）。
- Phase 5 在此基础上引入 TRNG 事务层，而非重做 Phase 4 输入层。

## Go/No-Go 规则（Phase 4）
- 任何一项验收门槛失败即 No-Go。
- 若 Gate 5/6/7 任一回归失败，立即停止扩展并回到治理修复。

## 建议执行节奏
- T+0：锁定 NPC state / resource mapping / interaction event 数据契约。
- T+1：完成 NPC 阈值进入判定与背包资源降级链路。
- T+2：完成交互事件到 realtime patch apply，并补齐 determinism/hash 审计测试。
- T+3：输出 Phase 4 首轮证据报告，满足后再进入 Phase 5（TRNG）。

## 执行任务板
- 详见：`docs/payload_v2/PHASE4_TASK_BOARD.md`（4 modules × 3 tasks）。

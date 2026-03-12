# Phase 4 任务板（4 Modules × 3 Tasks）

## 使用说明
- 本任务板仅覆盖 Phase 4（NPC + Interaction Runtime，TRNG 前）。
- 粒度固定为 4 个模块，每个模块 3 个任务，总计 12 个任务。
- 任何任务不得引入 TRNG begin/apply/commit/rollback。
- 实施落点与当前进度见：`docs/payload_v2/PHASE4_IMPLEMENTATION_MAP.md`。

## Module A：NPC Registry / State

### A1. 定义 `NPCState` 版本化结构
- 目标：落地 `NPCState.version` 与核心字段。
- 关键字段：`version`, `npc_id`, `relationship_value`, `threshold`, `npc_available`, `anchor`。
- DoD：结构定义固定，序列化可稳定输出，字段校验通过。

### A2. 实现关系阈值判定与 `npc_available`
- 目标：根据关系值阈值生成 NPC 准入决策。
- 规则：`relationship_value >= threshold` 时 `npc_available=true`。
- DoD：决策输出含 `npc_id/relationship_value/threshold/npc_available/decision`。

### A3. NPC 状态审计与哈希
- 目标：为状态快照提供可审计哈希。
- 规则：相同输入状态生成相同 `state_hash`。
- DoD：单测覆盖“同输入同 hash / 变更后 hash 改变”。

## Module B：Resource Mapping（只读绑定）

### B1. 定义 `ResourceInventory` 版本化结构
- 目标：落地玩家资源快照模型。
- 关键字段：`version`, `player_id`, `resources[]`, `timestamp`。
- DoD：可稳定加载与导出，缺失字段可识别。

### B2. 导入链路接入 missing_resources
- 目标：导入关卡仅使用背包可用资源。
- 规则：缺资源时降级为文字/轻量 patch，并写出 `missing_resources`。
- DoD：导入响应 trace 中可见 `missing_resources`，且降级行为稳定。

### B3. 资源绑定可审计
- 目标：记录资源绑定输入与决策结果。
- 输出：`resource_bindings`, `missing_resources`, `decision_reason`。
- DoD：同 inventory 输入，绑定结果与 hash 一致。

## Module C：Interaction Event Log

### C1. 定义 `InteractionEvent` 版本化结构
- 目标：统一事件模型（talk / collect / trigger）。
- 关键字段：`version`, `event_id`, `type`, `player_id`, `npc_id`, `anchor`, `timestamp`。
- DoD：事件结构可验证，字段约束明确。

### C2. 实现 append-only / immutable 事件日志
- 目标：日志只追加，不允许历史改写。
- 规则：禁止 update/delete 历史事件；event_id 单调递增或唯一有序。
- DoD：接口层拒绝改写操作，审计日志可证明 append-only。

### C3. 实现 `state = f(event_log)` reducer
- 目标：状态更新为 event_log 的确定性函数。
- 规则：相同 initial_state + event_log => 相同 runtime_state + state_hash。
- DoD：重建测试通过，状态重放一致。

## Module D：Realtime Patch Apply（非 TRNG）

### D1. 落地 Anchor Resolution Order
- 目标：固定 anchor 解析优先级并统一执行。
- 顺序：`player explicit anchor > scene anchor routing > npc anchor > default home anchor`。
- DoD：冲突场景下解析结果可预测且有 trace。

### D2. 定义 `WorldPatch` 版本化与强绑定字段
- 目标：patch 与输入状态强绑定。
- 关键字段：`version`, `patch_id`, `source_event`, `input_state_hash`, `payload_hash`, `anchor`, `timestamp`。
- DoD：每个 patch 均可追溯到 source_event 与 input_state_hash。

### D3. `EVENT_REPLAY_TEST`（强制）
- 目标：验证运行时重放一致性。
- 步骤：给定同一 `event_log`，重建 `runtime_state`，生成 `world_patch`。
- 断言：`state_hash` 一致、`payload_hash` 一致、patch 内容一致。
- DoD：测试纳入 Phase 4 必跑集合；失败即 No-Go。

## Phase 4 必跑最小测试集合
- NPC 阈值准入测试（含 `npc_available`）。
- 缺资源降级测试（含 `missing_resources` trace）。
- Anchor 优先级解析测试。
- EVENT_REPLAY_TEST（state_hash/payload_hash 一致性）。

## Go / No-Go
- 任一模块 DoD 未满足：No-Go。
- EVENT_REPLAY_TEST 失败：No-Go。
- Gate 5/6/7 回归失败：No-Go。

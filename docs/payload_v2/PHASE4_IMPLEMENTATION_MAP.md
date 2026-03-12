# Phase 4 实现映射（Execution Map）

## 执行顺序
- 固定顺序：Module C → Module A → Module B → Module D
- 已完成：Module C（Milestone 1 + Milestone 2）
- 本轮新增完成：Module A（A1 + A2 + A3）
- 本轮新增完成：Module B（B1 + B2 + B3）
- 本轮新增完成：Module D（D1 + D2 + D3）

## Milestone 状态
- Milestone 1：InteractionEvent model + append-only event log + reducer ✅
- Milestone 2：EVENT_REPLAY_TEST（same event_log → same state_hash → same payload_hash）✅
- Milestone 3：NPCState versioned structure + threshold 判定 + deterministic state_hash ✅
- Milestone 4：ResourceInventory versioned structure + missing_resources + deterministic binding_hash ✅
- Milestone 5：Anchor resolution + WorldPatch generator + replay patch determinism ✅

## Module C 映射（已实现）

### C1 InteractionEvent model
- 代码：`backend/app/core/runtime/interaction_event.py`
- 关键实现：
  - `InteractionEvent`（versioned）
  - `create_interaction_event(...)`
  - `coerce_interaction_event(...)`

### C2 append-only / immutable event log
- 代码：`backend/app/core/runtime/interaction_event_log.py`
- 关键实现：
  - `InteractionEventLog.append(...)`
  - duplicate event_id 拒绝
  - `update/delete/clear` 统一拒绝（IMMUTABLE_EVENT_LOG）

### C3 reducer（state = f(event_log)）
- 代码：`backend/app/core/runtime/state_reducer.py`
- 关键实现：
  - `reduce_event_log(...)`
  - `runtime_state_hash(...)`
  - `replay_event_log_to_patch(...)`
  - `build_world_patch_from_state(...)`（委托 world_patch generator，含 `input_state_hash`、`payload_hash`）

## Phase 4 Runtime 包入口
- 代码：`backend/app/core/runtime/__init__.py`

## Module A 映射（已实现）

### A1 NPCState versioned structure
- 代码：`backend/app/core/runtime/npc_state.py`
- 关键实现：
  - `NPCState`（versioned）
  - `create_npc_state(...)`
  - `normalize_npc_state(...)`

### A2 relationship threshold → npc_available
- 代码：`backend/app/core/runtime/npc_state.py`
- 关键实现：
  - `evaluate_npc_availability(...)`
  - `apply_relationship_delta(...)`
- reducer 接入：`backend/app/core/runtime/state_reducer.py`

### A3 deterministic state_hash
- 代码：`backend/app/core/runtime/npc_state.py`
- 关键实现：
  - `npc_state_hash(...)`
- reducer 接入：`backend/app/core/runtime/state_reducer.py`（`runtime_state` 增加 `npc_state` 聚合输出）

## Module B 映射（已实现）

### B1 ResourceInventory versioned structure
- 代码：`backend/app/core/runtime/resource_mapping.py`
- 关键实现：
  - `ResourceInventory`（versioned）
  - `create_resource_inventory(...)`
  - `normalize_resource_inventory(...)`

### B2 missing_resources detection
- 代码：`backend/app/core/runtime/resource_mapping.py`
- 关键实现：
  - `detect_missing_resources(...)`
  - `bind_resources_to_scene(...)`（缺资源返回 `DEGRADED` + `text_patch`）

### B3 deterministic binding hash
- 代码：`backend/app/core/runtime/resource_mapping.py`
- 关键实现：
  - `resource_binding_hash(...)`
- reducer 接入：`backend/app/core/runtime/state_reducer.py`（`runtime_state.inventory` 与 `payload.inventory_resources`）

## Module D 映射（已实现）

### D1 anchor resolution order
- 代码：`backend/app/core/runtime/world_patch.py`
- 关键实现：
  - `resolve_world_patch_anchor(...)`
  - 解析顺序：`player > scene > npc > home`

### D2 WorldPatch generator
- 代码：`backend/app/core/runtime/world_patch.py`
- 关键实现：
  - `generate_world_patch(...)`
  - `build_world_patch_payload(...)`
  - 输出字段：`version`, `patch_id`, `source_event`, `input_state_hash`, `payload_hash`, `anchor`, `timestamp`

### D3 EVENT_REPLAY_TEST 扩展
- 代码：`tests/test_phase4_event_runtime_module_c.py`
- 关键实现：
  - 增加 `world_patch` 全量一致性断言
  - 增加 `input_state_hash == state_hash` 与 `payload_hash` 对齐断言
- Module D 专项测试：`tests/test_phase4_world_patch_module_d.py`

## 测试映射（已通过）
- 测试文件：`tests/test_phase4_event_runtime_module_c.py`
- 覆盖点：
  - 事件类型校验
  - append-only / immutable
  - reducer 确定性
  - EVENT_REPLAY_TEST
- 测试文件：`tests/test_phase4_npc_state_module_a.py`
- 覆盖点：
  - NPCState version 字段与结构校验
  - 阈值判定与 `npc_available`
  - `npc_state_hash` 确定性
  - reducer `npc_state` 聚合输出
- 测试文件：`tests/test_phase4_resource_mapping_module_b.py`
- 覆盖点：
  - ResourceInventory version 字段与结构归一化
  - `missing_resources` 检测与 `DEGRADED/text_patch`
  - `resource_binding_hash` 确定性
  - reducer `inventory` 聚合输出与 patch payload 对齐
- 测试文件：`tests/test_phase4_world_patch_module_d.py`
- 覆盖点：
  - D1 锚点优先级（player > scene > npc > home）
  - D2 `WorldPatch` 必要字段与 hash 绑定
  - D3 same event_log → same world_patch / payload_hash

## 已执行验证
- `python3 -m pytest -q tests/test_phase4_event_runtime_module_c.py`
- `python3 -m pytest -q tests/test_trng_transaction_shell.py tests/test_phase4_event_runtime_module_c.py`
- `python3 -m pytest -q tests/test_phase4_npc_state_module_a.py tests/test_phase4_event_runtime_module_c.py tests/test_trng_transaction_shell.py`
- `python3 -m pytest -q tests/test_phase4_resource_mapping_module_b.py tests/test_phase4_npc_state_module_a.py tests/test_phase4_event_runtime_module_c.py tests/test_trng_transaction_shell.py`
- `python3 -m pytest -q tests/test_phase4_world_patch_module_d.py tests/test_phase4_resource_mapping_module_b.py tests/test_phase4_npc_state_module_a.py tests/test_phase4_event_runtime_module_c.py tests/test_trng_transaction_shell.py`

## 收口状态（已完成）
- Phase 4 收口报告：`docs/payload_v2/PHASE4_CLOSURE_REPORT.md`
- Evidence snapshot：`docs/payload_v2/evidence/phase4/snapshot_runtime_v1/PHASE4_EVIDENCE_SNAPSHOT.md`
- Gate 回归命令：`docs/payload_v2/PHASE4_GATE_REGRESSION_COMMANDS.md`

## 下一步（Phase 5 入口已就绪）
- Phase 5 启动清单（仅入口规范，未实现）：`docs/payload_v2/PHASE5_KICKOFF_CHECKLIST.md`

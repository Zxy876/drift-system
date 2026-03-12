# Phase5 M6 Closeout（Player Event Ingress）

日期：2026-03-05
状态：Closed（入口已打通，证据已封存）

## 1) M6 做了什么
- 插件侧新增玩家拾取事件监听：`EntityPickupItemEvent`，并通过 `RuleEventBridge.emitCollect(...)` 上报。
- 已复用既有入口：`POST /world/story/rule-event`（未引入新传输通道）。
- 后端 `world_api.story_rule_event` 增加桥接：`rule-event -> InteractionEvent -> TRNG begin/apply/commit`。
- 保持 Phase4 语义边界：未重写 reducer/world_patch，仅在入口做标准化与事务接入。
- 在 `DRIFT_DEBUG_TRACE=true` 时返回 `interaction_transaction` 摘要；默认不泄露调试字段。

## 2) 事件类型映射表（插件 -> InteractionEvent）

| Minecraft 侧事件 | plugin `event_type` | InteractionEvent.type | 说明 |
|---|---|---|---|
| 聊天 | `chat` | `talk` | 文本来源 `payload.text` |
| 方块交互 | `interact_block` | `trigger` | 由 `quest_event/event_type` 形成触发文本 |
| 实体交互 | `interact_entity` | `trigger` | 由 `quest_event/event_type` 形成触发文本 |
| 拾取物品 | `collect` | `collect` | 资源键 `resource/item_type`，数量 `amount` |

补充：后端映射规则支持 `collect/pickup/pickup_item/item_pickup -> collect`，`chat/talk -> talk`，其他默认 `trigger`。

## 3) 验证步骤（进服 3 动作 -> 3 次事务）
前置条件：
- 插件已更新到包含 pickup 监听的版本。
- 插件 `base_url` 指向已部署 M6 的后端。
- 建议开启：`DRIFT_ENABLE_PLUGIN_TRNG=true`。
- 需要可见事务摘要时开启：`DRIFT_DEBUG_TRACE=true`。

验收动作：
1. 拾取任意物品（pickup/collect）
2. 右键交互方块或实体（interact）
3. 发送一条聊天消息（chat）

期望结果（满足任一可观测路径即可）：
- `POST /world/story/rule-event` 返回中出现 `interaction_transaction.tx_id`（debug 模式）。
- 同一玩家连续三次动作可观测到事务提交（`tx_id` 变化）。
- 或后端日志可见 rule-event 收到对应类型并完成事务 ingest。

## 4) 最小回归命令（M6）
```bash
python3 -m pytest -q \
  backend/test_world_rule_event_trng_integration.py \
  backend/test_story_inject_trng_integration.py \
  backend/test_story_inject_payload_v2_gate4.py \
  backend/test_gate7_rollback_safety.py

python3 -m pytest -q \
  tests/test_trng_begin.py \
  tests/test_trng_apply.py \
  tests/test_trng_commit.py \
  tests/test_trng_rollback.py \
  tests/test_trng_transaction_shell.py

PYTEST_CURRENT_TEST=1 python3 tools/gate2_replay_determinism_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate2b_execution_replay_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate3_hash_consistency_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate4_strict_integrity_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate5_compatibility_rejection_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate6_rule_immutability_check.py && \
PYTEST_CURRENT_TEST=1 python3 tools/gate7_rollback_safety_check.py

python3 tools/gate_regression_snapshot.py
```

## 5) 已封存证据（本次收口）
- 快照目录：`docs/payload_v2/evidence/gate_regression/snapshot_20260304T164303Z/`
- 快照说明：`docs/payload_v2/evidence/gate_regression/snapshot_20260304T164303Z/GATE_REGRESSION_EVIDENCE_SNAPSHOT.md`
- 清单哈希：`docs/payload_v2/evidence/gate_regression/snapshot_20260304T164303Z/artifact_manifest.json`
- Kickoff 引用已更新：`docs/payload_v2/PHASE5_KICKOFF_CHECKLIST.md`

快速定位（进服无变化时优先检查）：
- 插件未更新（无 pickup 监听）。
- 后端未更新（`world_api.story_rule_event` 无 TRNG ingest）。
- 插件 `base_url` 指向错误环境。
- `DRIFT_DEBUG_TRACE` 未开启导致看不到事务摘要（但事务仍可能已执行）。
- 事件映射落入 `trigger` 路径时，上层业务未消费对应 `quest_event`。

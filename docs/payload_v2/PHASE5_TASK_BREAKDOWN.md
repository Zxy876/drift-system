# Phase 5 任务拆分（Design Freeze 后执行版）

## 目标
- 在不改动 Phase4 runtime pipeline 的前提下，引入 TRNG 事务壳层能力。
- 先做测试约束与任务拆分，再做最小实现，最后回归 Gate2~7。

## 不可破坏约束
- I1 Draft isolation
- I2 Atomic publish
- I3 Deterministic replay
- I4 Audit completeness
- I5 Rule immutability

## 事务边界（冻结）
- 允许新增：`begin_tx`、`apply_event`、`commit`、`rollback` 的壳层行为。
- 禁止修改：`event_log -> state_reducer -> runtime_state -> world_patch_generator` 语义。
- 禁止引入：并发控制、分布式提交、直接世界写入副作用。

## 里程碑拆分

### M1 - 测试骨架（本轮）
- 新建测试骨架文件：
  - `tests/test_trng_begin.py`
  - `tests/test_trng_apply.py`
  - `tests/test_trng_commit.py`
  - `tests/test_trng_rollback.py`
- 测试策略：Fail-first 占位，明确验收目标，不实现业务逻辑。

### M2 - 最小事务实现（下一轮）
- 仅补齐：`tx_context`、`draft_state`、`draft_patch`、`commit receipt`、`rollback receipt`。
- 不做任何 runtime core 改造。

### M3 - 事务不变量闭环（下一轮）
- 逐项点亮 T1~T6：
  - T1 isolation
  - T2 atomic
  - T3 rollback
  - T4 determinism
  - T5 reject
  - T6 gate compatibility

### M4 - 门禁回归与证据封存（实现后）
- 复跑 Gate2/Gate3/Gate4/Gate5/Gate6/Gate7。
- 重新生成 gate regression snapshot，更新 evidence manifest。

## 测试矩阵映射

| 编号 | 目标 | 对应骨架文件 |
|---|---|---|
| T1 | Draft isolation | `tests/test_trng_begin.py`, `tests/test_trng_apply.py` |
| T2 | Atomic publish | `tests/test_trng_commit.py` |
| T3 | Rollback safety | `tests/test_trng_rollback.py` |
| T4 | Deterministic replay (transactional) | `tests/test_trng_begin.py`, `tests/test_trng_apply.py` |
| T5 | Invariant reject path | `tests/test_trng_apply.py`, `tests/test_trng_rollback.py` |
| T6 | Gate compatibility | `tests/test_trng_commit.py` |

## 完成定义（DoD）
- M1 完成标准：骨架测试与任务文档齐备，尚未实现事务逻辑。
- M2 完成标准：最小事务壳层可运行，不变量尚未全绿可接受。
- M3 完成标准：T1~T6 全通过。
- M4 完成标准：Gate2~7 全绿并完成证据快照。

# TRNG Shell API（Phase 3A Freeze）

## 范围与边界
- 本文仅定义事务壳 API 契约。
- 不涉及 story engine 接线，不修改 mapper/projection/payload/executor。

## 1) 输入契约

### begin_tx(committed_graph, committed_state)
- 输入：
  - `committed_graph`: 已提交图状态
  - `committed_state`: 已提交内部状态
- 输出：
  - `Transaction`
- 约束：
  - `draft_graph` 和 `draft_state` 必须是 committed 的深拷贝。
  - begin 后不得修改 committed 对象。

### apply_event(tx, event)
- 输入：
  - `tx`: 事务对象
  - `event`: 事件字典（最小字段：`type`, `text`）
- 行为：
  - 生成至少一个节点写入 `tx.nodes` 与 `tx.draft_graph`。
  - 执行 `world_dry_run`（仅调用 adapter，不直接执行世界写入）。
  - dry-run 失败时追加 reject 节点。

## 2) 输出契约

### commit(tx, committed_graph, committed_state, rule_version)
- 成功返回：`(new_committed_graph, new_committed_state)`
- commit 必须写入：
  - `new_committed_state.rule_version`
  - `new_committed_state.world_patch_hash`（来自 dry-run 元数据）
- 失败行为：
  - 违反 invariant 时抛出 `InvariantViolation`
  - committed 输入不得被污染

### rollback(tx)
- 行为：
  - 标记 `tx.rolled_back = true`
  - 不写入 committed graph/state

## 3) Invariant 错误类型
- 异常类型：`InvariantViolation`
- 当前错误码集合（来自 invariant_check）：
  - `TX_MUST_CREATE_AT_LEAST_ONE_NODE`
  - `GRAPH_EMPTY_AFTER_TX`
  - `CURRENT_NODE_NOT_AT_GRAPH_TAIL`
  - `STATE_LAST_NODE_MISMATCH`
  - `PHASE_CHANGED_MORE_THAN_ONCE`
  - `GRAPH_SHRINK_NOT_ALLOWED`
  - `GRAPH_NOT_ADVANCED`
  - `SILENCE_COUNT_DECREASE_NOT_ALLOWED`

## 4) Commit Contract（冻结）
- 每次输入至少 1 节点。
- graph/state 同成同败。
- commit 前 draft 对外不可见。
- world execute 必须在 commit 后排队（after-commit enqueue）。

## 5) 版本锚点
- `rule_version`: 事务提交时必须显式传入并落盘到 committed state。
- `world_patch_hash`: 来自 dry-run，作为事务提交证据字段。

## 6) 非目标
- 不做 projection 决策。
- 不调用 executor。
- 不读取世界状态。
- 不暴露 story_api 入口。

## 7) 测试基线
- `docs/payload_v2/TRNG_SHELL_INVARIANT_CHECKLIST.md`

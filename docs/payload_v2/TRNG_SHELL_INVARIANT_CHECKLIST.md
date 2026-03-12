# TRNG Shell 最小不变量测试清单（工程级）

## 目标
- 为 Phase 3A 事务壳提供可重复、可审计的最小测试基线。
- 仅覆盖壳层行为，不涉及 story_engine 接线。

## 范围边界
- 允许：`transaction.py`、`graph_state.py`、`invariant_check.py`
- 禁止：修改 mapper/projection/payload/executor/story_api

## 必测清单（最小 6 条）

### INV-01 Draft 不可见
- 前置：`begin_tx` + `apply_event`
- 断言：`committed_graph` 与 `committed_state` 在 commit 前不变化

### INV-02 Commit 才可见
- 前置：`begin_tx` + `apply_event` + `commit`
- 断言：提交后 graph 增长，`last_node_id == current_node_id`

### INV-03 每事务至少一节点
- 前置：`begin_tx` 后直接 `commit`
- 断言：抛出 `InvariantViolation(TX_MUST_CREATE_AT_LEAST_ONE_NODE)`

### INV-04 Rollback 不污染 committed
- 前置：`begin_tx` + `apply_event` + `rollback`
- 断言：committed graph/state 保持原值

### INV-05 Invariant 失败不污染 committed
- 前置：构造事务后注入 invariant 失败条件（例如 phase_change_count > 1）
- 断言：`commit` 抛错，committed graph/state 不变

### INV-06 Dry-run fail 必须显式节点化
- 前置：注入 dry-run FAIL adapter，执行 `apply_event`
- 断言：追加 `reject` 节点（`event_type=world_reject`）

## 建议扩展（非 Phase 3A 必需）
- INV-07 `world_patch_hash` 在 commit 后写入 committed_state
- INV-08 `rule_version` 在 commit 后写入 committed_state
- INV-09 `GRAPH_NOT_ADVANCED` 保护
- INV-10 `STATE_LAST_NODE_MISMATCH` 保护

## 通过标准
- 最小 6 条全部 PASS。
- 所有失败路径均可复现，错误类型稳定。
- 测试执行不得依赖外部网络与世界状态。

## 证据归档建议
- 测试命令：`python3 -m pytest tests/test_trng_transaction_shell.py -q`
- 归档位置：
  - `docs/payload_v2/evidence/gate_trng/snapshot_rule_v2_2/`
  - 包含：测试输出、commit hash、脚本指纹

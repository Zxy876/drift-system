# Phase 3 启动门禁清单（Gate Checklist）

## 目的
- 本文用于判定 Drift 是否可以从 Phase 2.2 进入 Phase 3（executor/replay 升级实施期）。
- 本文是安全门禁，不是排期文档。

## 结构入口
- 控制层级总览见：`PHASE0_TO_PHASE3_ARCHITECTURE.md`

## Gate 1 — Schema Freeze
**目标**：协议边界冻结，禁止隐式漂移。

### 必须满足
- `plugin_payload_schema_v2.json` 字段集合冻结（无新增/删除/重命名）。
- `ENTITY_HASH_CANONICALIZATION_RULES.md` 冻结并已评审通过。
- 默认规则版本锁定为 `rule_v2_2`。

### 证据
- schema 文件哈希记录。
- 评审记录（PR/ADR）。
- registry 版本快照。

### 失败处理
- 任一项未满足：**禁止进入 Phase 3**。

---

## Gate 2 — Replay Determinism
**目标**：回放可复现，不依赖 runtime 波动。

### 必须满足
- `replay_v2` 可稳定复现以下场景：
  - fog-only
  - npc-only
  - fog + npc
- 每个场景 100 次 replay 的最终 hash 完全一致。

### 证据
- 批量回放报告（100 次统计）。
- 场景级 hash 对比表。

### 失败处理
- 任一场景出现 hash 漂移：**阻断 Phase 3**。

---

## Gate 3 — Hash Consistency
**目标**：跨版本 hash 语义不混淆。

### 必须满足
- payload_v1 的 block-only hash 结果不变。
- payload_v2 的 block+entity hash 结果稳定。
- canonical 排序规则有独立单测覆盖。

### 证据
- v1 回归 hash 报告。
- v2 canonical hash 测试报告。
- 排序规则测试清单。

### 失败处理
- 任一版本 hash 语义不稳定：**阻断 Phase 3**。

---

## Gate 4 — Strict Reject Integrity
**目标**：strict 模式失败语义可证明、可审计。

### 必须满足
- strict 下 unsupported entity 返回 422。
- strict 失败时不生成 `final_commands_hash`。
- strict 失败时不落盘。
- strict 失败时 trace 字段完整。

### 证据
- API 422 响应样例。
- 落盘隔离检查日志。
- trace 字段断言报告。

### 失败处理
- 存在 silent fail 或落盘污染：**阻断 Phase 3**。

---

## Gate 5 — Compatibility Rejection
**目标**：不兼容路径明确拒绝，不猜测、不容错。

### 必须满足
- v1 executor 收到 payload_v2 必须明确拒绝。
- 拒绝错误码稳定（建议：`UNSUPPORTED_PAYLOAD_VERSION`）。
- 不允许 silent fail 或隐式降级执行。

### 证据
- 兼容矩阵验收报告。
- 错误码稳定性测试。

### 失败处理
- 拒绝行为不稳定：**阻断 Phase 3**。

---

## Gate 6 — Projection Rule Immutability
**目标**：规则版本冻结，禁止就地修改历史规则。

### 必须满足
- `projection_rule_registry` 中 `rule_v2_2` 不可修改。
- 规则变更必须新建 `rule_v2_3+`。
- 旧版本 replay 路径可继续运行。

### 证据
- registry 变更审计记录。
- rule_version 升级 PR 模板检查。

### 失败处理
- 发现就地修改：**阻断 Phase 3**。

---

## Gate 7 — Rollback Safety
**目标**：升级可撤销，生产可恢复。

### 必须满足
- 可通过 feature flag 回退到 payload_v1 only。
- 可回退到 `scene_orchestrator_v1`。
- 回退后构建链路可用，关键回归通过。

### 证据
- 回退演练记录。
- 回退后健康检查结果。

### 失败处理
- 回退路径不完整：**阻断 Phase 3**。

---

## 启动判定规则
- 7 个 Gate 必须全部通过，才能进入 Phase 3 实施。
- 任一 Gate 失败即维持在 Phase 2.2，先修复再复评。

## 附：评审模板（简版）
- Gate ID:
- 结论：PASS / FAIL
- 证据链接：
- 发现问题：
- 修复负责人：
- 复评日期：

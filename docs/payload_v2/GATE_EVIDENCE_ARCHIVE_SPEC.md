# Gate Evidence Archive Spec

## 目的
- 为 Gate 证据建立可回溯、可审计、可版本化的归档规范。
- 确保每一次 PASS/FAIL 都绑定确定的代码与规则上下文。

## 1) Snapshot Trigger Rules
出现以下任一变更，必须生成新的 Gate 证据快照：
- rule_version 升级。
- schema_version 升级。
- hash canonicalization 规则变更。
- projection rule 变更（新增/删除/参数调整）。
- executor 或 replay 逻辑变更。

## 2) Mandatory Anchors
每个快照必须包含以下锚点字段：
- commit_hash
- rule_version
- engine_version
- schema_version
- replay_engine_version
- artifact_manifest

建议额外字段：
- generated_at_utc
- gate_scope（例如：projection-layer / execution-layer）
- limitations（例如：no real summon replay）

## 3) Evidence Storage Layout
证据必须按 Gate 与快照版本分目录存储：

```text
docs/payload_v2/evidence/
  ├── gate2/
  │   ├── snapshot_rule_v2_2/
  │   │   ├── GATE2_EVIDENCE_SNAPSHOT.md
  │   │   ├── artifact_manifest.json
  │   │   ├── replay_report.json
  │   │   └── execution_report.json
```

规则：
- 不将新证据直接写入 evidence 根目录。
- 每个快照目录只对应一个规则/版本基线。

## 4) Immutability Policy
- 已归档 snapshot 不得修改。
- 发现错误时不得覆盖旧快照，必须新增修订目录：
  - 例如：snapshot_rule_v2_2_rev2
- 任何覆盖写都视为审计违规。

## 5) Revalidation Protocol
当 rule_version 升级时：
- 必须重跑相关 Gate。
- 不允许沿用旧 PASS。
- 必须生成新 snapshot 并更新 precheck 状态。

## 6) Naming Convention
- Gate 目录：gate1, gate2, ...
- 快照目录：snapshot_rule_vX_Y 或 snapshot_rule_vX_Y_revN
- 核心文件名固定：
  - GATEX_EVIDENCE_SNAPSHOT.md
  - artifact_manifest.json
  - 对应 gate 的报告文件（如 replay_report.json）

## 7) Minimum Acceptance for Archive
一次快照归档完成的最低条件：
- 目录结构完整。
- manifest 中所有工件存在且 SHA256 可复验。
- 快照文档中声明 scope 与 limitations。
- precheck 报告可链接到该快照路径。

## 当前基线
- Gate 2 当前归档路径：
  - docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/

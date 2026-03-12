# Drift Payload v2 Mapping Failure Policy (Draft v0)

## 背景
- Drift v2 默认策略为 **B：可证明降级**。
- 可选运行模式：`strict_mode=true` 时切换为 **A：强拒绝**。
- 本文目标：固定“无法 deterministic 映射 scene 语义”时的 **Fail/Degrade 决策真值表**。
- 本文仅定义策略与验收约束，不包含代码、schema 变更或运行逻辑修改。

## 术语与动作枚举
- `DEGRADE_TO_STRUCTURE`：降级到结构语义可执行路径。
- `DROP_SEMANTICS`：丢弃不可映射语义字段，继续执行其余可映射部分。
- `KEEP_METADATA_ONLY`：仅保留元数据与 trace，不产生新增执行语义。
- `REJECT`：拒绝本次构建并返回 `failure_code`。
- `fallback_path`：固定记录降级路径，例如 `v2->structure_spec->v1_commands`。

## 冻结判定常量（用于机器可判定触发）
- `REQUIRED_SCENE_FIELDS = {"scene_type", "time_of_day", "weather", "mood"}`。
- `missing_fields = REQUIRED_SCENE_FIELDS - keys(scene_spec)`。
- `ENUMS` 的 SSoT 固定为 `rule_version`（不是 `engine_version`）：
	- `ENUMS[rule_version].scene_type = {"lake", "village", "forest", "plain"}`
	- `ENUMS[rule_version].time_of_day = {"day", "night"}`
	- `ENUMS[rule_version].weather = {"clear", "rain"}`
	- `ENUMS[rule_version].mood = {"calm", "tense", "mysterious"}`
- `top_candidates`：来自 mapper 内部候选集（同样必须写入 `trace.mapper_decisions[].candidates[]`），每项必须含 `id` 与 `score`。
- `MAX_STRUCTURE_BLOCKS`：结构阈值（冻结在规则版本中）。

## Definitions（术语冻结）

| 变量 | 类型 | 来源 | 判定方法 | 是否进入 trace |
|---|---|---|---|---|
| `expected_catalog_version` | `string` | 规则配置（`rule_version` 对应映射） | `catalog_version == expected_catalog_version` | 是（`catalog_version`） |
| `catalog_loaded` | `bool` | binder 载入结果 | `catalog_load_result.status == SUCCESS` | 是 |
| `resource_id` | `string` | binder 输入绑定请求 | `resource_id in catalog.resource_ids` | 是（`resource_bindings[]`） |
| `rule_registry` | `object` | 规则注册中心快照 | `has_version(rule_version)` 与 `ruleset_integrity_check(rule_version)` | 否（结果入 trace） |
| `projection_supported` | `bool` 函数结果 | mapper 能力矩阵（`engine_version`） | `projection_supported(engine_version, target_semantic)` | 否（结果入 trace） |
| `SUPPORTED_NPC_PRIMITIVES` | `map<string,set<string>>` | 引擎能力矩阵（按 `engine_version` 冻结） | `requested in SUPPORTED_NPC_PRIMITIVES[engine_version]` | 否（结果入 trace） |
| `validator_result` | `object` | validator 输出 | `validator_result.failure_code in {...}` | 是 |
| `predicted_blocks` | `int` | mapper/binder 预估值 | `predicted_blocks >= 0` 且用于 guardrail 判定 | 是 |
| `structure_block_count` | `int` | validator 对最终 patch 的真实计数 | `structure_block_count >= 0` | 是 |
| `conflict_priority_equal` | `bool` | merge 冲突分析 | 冲突双方 `priority_a == priority_b` | 是（`mapper_decisions[]`） |
| `tiebreak_rule_found` | `bool` | merge 规则查询结果 | `tiebreak_rule_found == true/false` | 是（`mapper_decisions[]`） |

附加一致性约束：`predicted_blocks >= structure_block_count`。若不成立，判定为规则/预估器错误，触发 `REJECT`（`failure_code=PREDICTION_UNDERFLOW`）。

## 决策表（B 默认 + strict=A）

| trigger | stage | default_action | strict_action | failure_code | degrade_reason | lost_semantics[] | trace_required | must_not |
|---|---|---|---|---|---|---|---|---|
| `len(missing_fields) > 0` | scene_spec | DEGRADE_TO_STRUCTURE | REJECT | MISSING_SCENE_FIELD | SCENE_SPEC_INCOMPLETE | `SCENE.*` | `input_text_hash, scene_spec_hash, rule_version, engine_version, degrade_reason, lost_semantics, fallback_path` | 不得补猜缺失字段；不得调用外部资源补全 |
| `scene_spec.weather not in ENUMS[rule_version].weather` 或其他枚举字段不在对应 `ENUMS[rule_version]` | scene_spec | DROP_SEMANTICS | REJECT | INVALID_SCENE_ENUM | SCENE_ENUM_UNSUPPORTED | 对应非法字段（如 `ENVIRONMENT.weather`） | `scene_spec_hash, mapper_decisions, degrade_reason, lost_semantics, rule_version` | 不得隐式替换为随机合法值 |
| `len(top_candidates) >= 2 and top_candidates[0].score == top_candidates[1].score` | mapper | KEEP_METADATA_ONLY | REJECT | AMBIGUOUS_SCENE_INTENT | SCENE_AMBIGUOUS_TOP_TIE | 发生并列的语义字段 | `input_text_hash, scene_spec_hash, mapper_decisions(candidates/score/tie), degrade_reason` | 不得随机打破并列 |
| `catalog_loaded == false` 或 `catalog_version != expected_catalog_version` | binder | KEEP_METADATA_ONLY | REJECT | CATALOG_UNAVAILABLE | CATALOG_VERSION_OR_LOAD_FAILED | `RESOURCE_BINDING.*` | `catalog_version, engine_version, degrade_reason, fallback_path` | 不得以隐式默认 catalog 继续执行 |
| `catalog_loaded == true and resource_id not in catalog.resource_ids` | binder | DEGRADE_TO_STRUCTURE | REJECT | RESOURCE_ID_NOT_FOUND | RESOURCE_UNRESOLVED | `RESOURCE_BINDING.*` + `SCENE.* (if dependent_on_resource_binding == true)` | `catalog_version, mapper_decisions, resource_bindings, degrade_reason, lost_semantics, fallback_path` | 不得访问未声明资源；不得动态下载资源 |
| `rule_registry.has_version(rule_version) == false` | mapper | DEGRADE_TO_STRUCTURE | REJECT | RULESET_NOT_FOUND | RULESET_MISSING | `MAPPING.*` | `rule_version, mapper_decisions, degrade_reason, fallback_path` | 不得使用未冻结规则版本 |
| `rule_registry.has_version(rule_version) == true and ruleset_integrity_check(rule_version) == FAIL`（如 ruleset 文件缺失/解析失败/rule_index 缺失） | mapper | DEGRADE_TO_STRUCTURE | REJECT | RULE_MISSING | RULE_ENTRY_MISSING | `MAPPING.*` | `rule_version, mapper_decisions, degrade_reason, fallback_path` | 不得跳过缺失规则继续判定 |
| `guardrail_check == FAIL`（如 `predicted_blocks > MAX_STRUCTURE_BLOCKS` 或 `blocked_block_id_detected == true`） | binder | DEGRADE_TO_STRUCTURE | REJECT | GUARDRAIL_VIOLATION | RESOURCE_GUARDRAIL_BLOCKED | `RESOURCE_BINDING.*` | `mapper_decisions(candidates/reject_reason), resource_bindings, degrade_reason, lost_semantics, fallback_path` | 不得绕过 guardrails |
| `projection_supported(engine_version, target_semantic) == false` 且 `target_semantic in {ATMOSPHERE.*, LIGHTING.*, SOUND.*}` | mapper | DROP_SEMANTICS | REJECT | EXEC_CAPABILITY_GAP | NON_PROJECTABLE_SCENE_EFFECT | `ATMOSPHERE.*, LIGHTING.*, SOUND.*` | `engine_version, mapper_decisions, degrade_reason, lost_semantics, fallback_path` | 不得伪造等价效果 |
| `requested_npc_primitive not in SUPPORTED_NPC_PRIMITIVES[engine_version]` | mapper | DROP_SEMANTICS | REJECT | NPC_BEHAVIOR_UNSUPPORTED | NPC_PRIMITIVE_UNSUPPORTED | `NPC_BEHAVIOR.*` | `engine_version, mapper_decisions, degrade_reason, lost_semantics` | 不得生成未定义行为脚本 |
| `structure_block_count > MAX_STRUCTURE_BLOCKS` | validator | REJECT | REJECT | STRUCTURE_TOO_LARGE | — | — | `rule_version, mapper_decisions, failure_code, final_commands_hash` | 不得忽略容量阈值 |
| `exists_conflict and conflict_priority_equal == true and tiebreak_rule_found == false` | mapper | KEEP_METADATA_ONLY | REJECT | MERGE_CONFLICT_UNRESOLVED | CONFLICT_NO_TIEBREAKER | 冲突来源语义字段 | `mapper_decisions(conflict_pairs/priority/no_tiebreak), degrade_reason` | 不得使用随机 tie-break |
| `validator_result.failure_code in {INVALID_BLOCK_ID, INVALID_COORD, TOO_MANY_BLOCKS, EMPTY_BLOCKS}` | validator | REJECT | REJECT | `validator_result.failure_code` | — | — | `final_commands_hash, mapper_decisions, failure_code` | 不得跳过 validator |
| executor 队列满 | executor | REJECT | REJECT | EXECUTOR_QUEUE_FULL | — | — | `engine_version, failure_code, final_commands_hash` | 不得丢弃 trace 后重试 |
| `build_id` 冲突（`DUPLICATE_BUILD_ID`） | executor | REJECT | REJECT | DUPLICATE_BUILD_ID | — | — | `input_text_hash, scene_spec_hash, final_commands_hash, failure_code` | 不得自动改写 build_id |

## Trigger 匹配顺序与同 stage 内排序（保证 AC-02）
- 固定 stage 顺序：`scene_spec -> mapper -> binder -> validator -> executor`。
- 校验顺序强约束：必须 `validate-then-enqueue`，即 validator 在 executor 入队前完成；禁止 `enqueue-then-validate`。
- 同一 stage 命中多个 trigger 时，按“更基础依赖先判定”排序，取首个命中 trigger：
	- `scene_spec`：`MISSING_SCENE_FIELD > INVALID_SCENE_ENUM`。
	- `mapper`：`RULESET_NOT_FOUND > RULE_MISSING > AMBIGUOUS_SCENE_INTENT > EXEC_CAPABILITY_GAP > NPC_BEHAVIOR_UNSUPPORTED > MERGE_CONFLICT_UNRESOLVED`。
	- `binder`：`CATALOG_UNAVAILABLE > RESOURCE_ID_NOT_FOUND > GUARDRAIL_VIOLATION`。
	- `validator`：`STRUCTURE_TOO_LARGE > INVALID_BLOCK_ID > INVALID_COORD > TOO_MANY_BLOCKS > EMPTY_BLOCKS`。
	- `executor`：`EXECUTOR_QUEUE_FULL > DUPLICATE_BUILD_ID`。
- 排序规则冻结在 `rule_version`；未显式升级版本时不得变更。

## 语义字段枚举（稳定集合）
- `SCENE.scene_type`
- `SCENE.mood`
- `SCENE.contrast_level`
- `ENVIRONMENT.weather`
- `ENVIRONMENT.biome_tone`
- `LIGHTING.time_of_day`
- `LIGHTING.temperature`
- `ATMOSPHERE.fog`
- `ATMOSPHERE.particle_profile`
- `SOUND.ambient`
- `SOUND.music_cue`
- `NPC_BEHAVIOR.patrol`
- `NPC_BEHAVIOR.reaction_profile`
- `RESOURCE_BINDING.palette`
- `RESOURCE_BINDING.style_pack`

## Trace 义务（最小必含）
- `input_text_hash`
- `scene_spec_hash`
- `rule_version`
- `catalog_version`
- `engine_version`
- `mapper_decisions[]`（每条必须含：候选集、优先级、丢弃原因、冲突裁决）
- `degrade_reason`（发生降级时必填）
- `lost_semantics[]`（发生降级时必填）
- `fallback_path`（发生降级时必填）
- `final_commands_hash`

## 验收条款映射（12 条）

### 验收条款定义
- `AC-01` 成功确定性：同输入生成同 `world_patch`。
- `AC-02` 失败确定性：同输入同 `failure_code` 与拒绝阶段。
- `AC-03` 变更可追溯：每条 world 变更可追溯到 scene 字段。
- `AC-04` 规则命中可追溯：记录 `rule_id/rule_version/priority`。
- `AC-05` 资源选择可追溯：记录 `resource_id` 与候选筛选理由。
- `AC-06` 决策完备性：必须记录冲突裁决与丢弃原因。
- `AC-07` 回放确定性：environment/lighting/atmosphere/npc 可回放。
- `AC-08` LLM 限权：不得直接输出执行命令与资源绑定结果。
- `AC-09` 哈希闭环：`input/scene/final_commands` 哈希闭环可验证。
- `AC-10` 降级可证明：降级时必须有原因、损失语义、路径。
- `AC-11` 版本冻结：`rule/catalog/engine` 三元组必填。
- `AC-12` v2->v1 一致性：降级后命令哈希一致。

### 映射关系
| 验收条款 | 本文对应条目 |
|---|---|
| AC-01 | 决策表中的可判定 trigger + `must_not` 的“禁止随机裁决”约束 |
| AC-02 | 决策表 `strict_action` + `failure_code` 列 + “Trigger 匹配顺序与同 stage 内排序”章节 |
| AC-03 | 决策表 `lost_semantics[]` + Trace 义务 `mapper_decisions[]` |
| AC-04 | Trace 义务 `rule_version` + `mapper_decisions[]`（优先级/命中记录） |
| AC-05 | 决策表中 binder 相关行 + Trace 义务 `resource_bindings[]` |
| AC-06 | 决策表冲突类 trigger + Trace 义务 `mapper_decisions[]` |
| AC-07 | 决策表中 environment/lighting/atmosphere/npc 能力缺口行 + `fallback_path` |
| AC-08 | 决策表 `must_not` 列（禁止 LLM 直出坐标/命令/绑定） |
| AC-09 | Trace 义务中的 `input_text_hash/scene_spec_hash/final_commands_hash` |
| AC-10 | 决策表 `degrade_reason` 与 `lost_semantics[]` 列 + Trace 同名字段 |
| AC-11 | Trace 义务 `rule_version/catalog_version/engine_version` |
| AC-12 | 决策表的 `fallback_path` 与 `final_commands_hash` 一致性约束 |

## 系统认知对齐（一句话）
这份表不是描述性文档，而是 Drift v2 在“无法映射”场景下必须遵守的 Fail/Degrade 决策真值表，任何偏离都视为 bug。
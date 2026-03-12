# Projection Rule Registry Template (Phase 2.1)

## 目标
- 规则作为数据冻结，不在投影代码里硬编码参数。
- 通过 `rule_version` 演进能力，保障旧关卡 replay 不被新规则破坏。

## Registry 结构

```yaml
rule_version: rule_v2_2
projection_rules:
  atmosphere.fog:
    rule_id: PROJECTION_ATMOSPHERE_FOG_V1
    priority: 300
    stage: mapper
    block: glass_pane
    y_offset: 1
    fill_mode: full
    conflict_policy: skip_on_structure
    supported_engines:
      - engine_v2_1
  npc_behavior.lake_guard:
    rule_id: PROJECTION_NPC_LAKE_GUARD_V1
    priority: 350
    stage: mapper
    block: npc_placeholder
    x_offset: 2
    y_offset: 0
    z_offset: 0
    entity_type: villager
    name: Lake Guard
    profession: none
    ai_disabled: true
    silent: true
    rotation: 90
    conflict_policy: skip_on_structure
    supported_engines:
      - engine_v2_1
```

## 冻结约束
- 同一 `rule_version` 下以下字段不可变：
  - `rule_id`
  - `priority`
  - `block`
  - `y_offset`
  - `fill_mode`
  - `conflict_policy`
  - `supported_engines`
- 任何字段变更必须：
  1. 新建 `rule_version`（如 `rule_v2_3`）
  2. 复制旧规则后修改
  3. 保留旧版本供历史 replay 使用

## 演进策略
- 新增语义（例如 `atmosphere.mist`、`atmosphere.fog_density`）必须以新增规则项进入新 `rule_version`。
- 禁止在旧 `rule_version` 上就地修改已有规则。
- `npc_behavior` L1 仅允许静态 deterministic 投影：禁止 tick、schedule、pathfinding、行为树、外部 LLM。

## Trace 义务
- 每次投影命中必须记录：
  - `rule_id`
  - `priority`
  - `effect`
  - `projection_blocks_added`
  - `conflict_blocks_skipped`
  - `conflict_policy`
  - `block_id`
  - `y_offset`
  - `fill_mode`

## 最小回归清单
- `fog only` → `mapping_status=OK`，有投影块。
- `fog + low_music` (default) → `mapping_status=OK`，`lost_semantics=["sound.low_music"]`。
- `fog + low_music` (strict) → `mapping_status=REJECTED`，`failure_code=EXEC_CAPABILITY_GAP`。

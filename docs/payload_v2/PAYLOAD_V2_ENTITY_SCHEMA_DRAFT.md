# Payload v2 Entity Schema Draft (Deterministic / Replay-safe)

## 目标
- 在不破坏 v1 回放的前提下，引入实体操作（`summon`）。
- 保持 deterministic、auditable、replayable。
- 明确 unsupported 的降级与 strict 拒绝路径。

## 非目标
- 不引入 tick 驱动行为。
- 不引入路径寻路、行为树、对话 AI。
- 不读取世界状态作为决策输入。

## 顶层结构（草案）

```json
{
  "version": "plugin_payload_v2",
  "build_id": "string",
  "player_id": "string",
  "build_path": "string",
  "patch_source": "string",
  "scene_path": "string",
  "hash": {
    "scene_spec": "sha256",
    "spec": "sha256",
    "final_commands": "sha256"
  },
  "stats": {
    "scene_block_count": 0,
    "spec_block_count": 0,
    "merged_block_count": 0,
    "entity_command_count": 0,
    "conflicts_total": 0,
    "spec_dropped_total": 0
  },
  "origin": {
    "base_x": 0,
    "base_y": 64,
    "base_z": 0,
    "anchor_mode": "player"
  },
  "commands": [
    {
      "type": "setblock",
      "x": 0,
      "y": 64,
      "z": 0,
      "block": "stone"
    },
    {
      "type": "summon",
      "entity_type": "villager",
      "x": 2,
      "y": 64,
      "z": 0,
      "name": "Lake Guard",
      "profession": "none",
      "no_ai": true,
      "silent": true,
      "rotation": 90
    }
  ]
}
```

## Command 联合类型（最小集）
- `setblock`（沿用 v1）
- `summon`（新增）

### setblock 约束
- 必填：`type,x,y,z,block`
- `type` 固定为 `setblock`
- 坐标与方块 id 继续沿用白名单校验

### summon 约束
- 必填：`type,entity_type,x,y,z,name,profession,no_ai,silent,rotation`
- `type` 固定为 `summon`
- `entity_type` 初期白名单：`["villager"]`
- 不允许自由 `nbt` 注入
- `NoAI=true`、`Silent=true` 必须强制
- `Rotation` 必须由规则冻结值给出（不可运行时随机）

## Determinism 约束
- `commands` 必须稳定排序：
  - 先按 `type`（`setblock` < `summon`）
  - 再按坐标 `(x,y,z)`
  - 再按稳定字段字典序
- `final_commands` 是唯一执行源，`hash.final_commands` 必须覆盖 block + entity 两类命令。
- 任意 `rule_version` 不得就地修改旧规则参数，变更必须升版本。

## Projection Registry 绑定（示例）

```yaml
rule_version: rule_v2_3
projection_rules:
  npc_behavior.lake_guard:
    rule_id: PROJECTION_NPC_LAKE_GUARD_V2
    priority: 350
    stage: mapper
    command_type: summon
    entity_type: villager
    name: Lake Guard
    profession: none
    x_offset: 2
    y_offset: 0
    z_offset: 0
    no_ai: true
    silent: true
    rotation: [90.0, 0.0]
    conflict_policy: skip_on_structure
    supported_engines:
      - engine_v2_2
```

## strict/default 行为
- default：可投影语义执行；不可投影语义进入 `lost_semantics`。
- strict：任何不可投影语义直接 `REJECT`，`failure_code=EXEC_CAPABILITY_GAP`。

## 兼容策略
- v1 payload 不变，继续只处理 `setblock`。
- v2 payload 通过新 schema + 新 validator + 新 executor 通道处理。
- 同一关卡回放时必须绑定 `version + rule_version + engine_version`。

## 最小验收
1. `npc_behavior.lake_guard` 单独输入：`mapping_status=OK`，生成 1 条 `summon`。
2. `lake_guard + low_music` default：`OK`，`lost_semantics=["sound.low_music"]`。
3. 同输入重复构建：`hash.final_commands` 完全一致。
4. strict 模式含不支持语义：`REJECT + EXEC_CAPABILITY_GAP`。
5. 历史 v1 关卡回放结果不变。

# Validator v2 Pseudocode (Draft)

## 目标
- 独立于 v1 validator。
- 校验 union commands（`setblock` + `summon`）。
- 严格禁止非白名单实体字段。

## Pseudocode

```text
function validate_payload_v2(payload):
  require payload.version == "plugin_payload_v2"
  require payload.payload_version in {"v2", "v2.1"}
  require non_empty(payload.rule_version, payload.engine_version)

  schema_validate(payload, plugin_payload_schema_v2.json)

  setblock_count = 0
  summon_count = 0

  for cmd in payload.commands:
    if cmd.type == "setblock":
      validate_world_coord(cmd.x, cmd.y, cmd.z)
      validate_block_whitelist(cmd.block)
      setblock_count += 1
      continue

    if cmd.type == "summon":
      require cmd.entity_type == "villager"
      validate_world_coord(cmd.x, cmd.y, cmd.z)
      require cmd.no_ai == true
      require cmd.silent == true
      require cmd.profession == "none"
      require 0 <= cmd.rotation <= 359
      require no_extra_fields(cmd)
      summon_count += 1
      continue

    reject("INVALID_COMMAND_TYPE")

  require payload.stats.entity_command_count == summon_count

  if payload.payload_version == "v2.1":
    require payload.anchor in keys(payload.anchors)
    for op in payload.block_ops:
      require op.anchor in keys(payload.anchors)
      require len(op.offset) == 3

    for op in payload.entity_ops:
      require op.anchor in keys(payload.anchors)
      require len(op.offset) == 3

  canonical_commands = canonicalize_commands(payload.commands)
  expected_hash = sha256(json_dumps(canonical_commands, sort_keys=true, separators=(",", ":")))
  require payload.hash.final_commands == expected_hash

  return VALID
```

## 失败码建议
- `INVALID_PAYLOAD_VERSION`
- `INVALID_COMMAND_TYPE`
- `INVALID_ENTITY_COMMAND`
- `INVALID_ENTITY_FIELD`
- `FINAL_COMMANDS_HASH_MISMATCH`

## 约束
- 不读取世界状态。
- 不做运行时回填。
- 不做容错自动修复。

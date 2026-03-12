# Entity Hash Canonicalization Rules (Draft)

## 目标
冻结 `final_commands_hash` 规则，确保 block/entity 混合命令在 replay 中可重复。

## Canonicalization

1. 命令统一为标准对象，不允许额外键。
2. 排序键冻结为：
   - `type_order`: `setblock`=0, `summon`=1
   - `x` 升序
   - `y` 升序
   - `z` 升序
   - `payload_key`: 对命令对象做 key-sorted JSON 串
3. 序列化冻结为：
   - UTF-8
   - `json.dumps(..., ensure_ascii=false, sort_keys=true, separators=(",", ":"))`
4. 哈希算法冻结为 `sha256`。

## 伪代码

```text
TYPE_ORDER = {"setblock": 0, "summon": 1}

function canonicalize_commands(commands):
  normalized = [normalize_command(c) for c in commands]
  normalized.sort(
    key=(TYPE_ORDER[c.type], c.x, c.y, c.z, stable_json(c))
  )
  return normalized

function final_commands_hash(commands):
  canonical = canonicalize_commands(commands)
  payload = stable_json(canonical)
  return sha256(payload)
```

## 兼容规则
- v1 继续使用 `hash.merged_blocks`。
- v2 使用 `hash.final_commands`。
- replay 分流依据：`version`。

## 禁止项
- 禁止按输入顺序直接 hash。
- 禁止浮点随机化。
- 禁止在 hash 前注入运行时字段（如 tick、latency、executor id）。

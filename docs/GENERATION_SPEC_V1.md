# Drift Generation Spec v1.0

## 1) 目标

将生成链路从“LLM 直接出 world_patch”升级为“语义提案 + 确定性构建 + 显式执行结果”。

核心约束：

- LLM 只生成语义 Spec，不生成 block 坐标。
- Build Engine 只吃 Spec，不吃自然语言。
- 执行层禁止隐式 fallback，非法输入直接拒绝。

---

## 2) Spec Schema（v1）

```json
{
  "structure_type": "house | tower | wall | bridge",
  "width": 7,
  "depth": 5,
  "height": 4,
  "material_preference": "wood | stone | brick",
  "roof_type": "flat | gable | none"
}
```

### 字段约束

- `structure_type`：必填，枚举。
- `width`：必填，整数，范围 `3..64`。
- `depth`：必填，整数，范围 `3..64`。
- `height`：必填，整数，范围 `2..64`。
- `material_preference`：必填，枚举。
- `roof_type`：必填，枚举。

### 生成约束

- LLM 请求必须使用 `response_format=json_object`。
- LLM 生成温度固定 `temperature=0`。
- LLM 输出中出现 `blocks` / `build` / `mc` 等执行字段即判定无效。

---

## 3) 验证结果协议（Spec Validator）

```json
{
  "status": "VALID | REJECTED",
  "failure_code": "NONE | MISSING_FIELD | INVALID_ENUM | OUT_OF_RANGE | FORBIDDEN_EXEC_FIELD",
  "message": "human readable",
  "spec": {"...": "normalized spec when VALID"}
}
```

### failure_code 语义

- `MISSING_FIELD`：缺失必填字段。
- `INVALID_ENUM`：枚举字段非法。
- `OUT_OF_RANGE`：尺寸越界。
- `FORBIDDEN_EXEC_FIELD`：出现执行层字段。

---

## 4) Build Engine 输入输出协议

输入（仅 Spec）：

```json
{
  "spec": {
    "structure_type": "house",
    "width": 7,
    "depth": 5,
    "height": 4,
    "material_preference": "wood",
    "roof_type": "flat"
  }
}
```

输出（抽象块，不含 MC 材质 ID）：

```json
{
  "build_status": "SUCCESS | REJECTED",
  "failure_code": "NONE | INVALID_SPEC | UNSUPPORTED_STRUCTURE",
  "blocks": [
    {"x": 0, "y": 0, "z": 0, "role": "FLOOR"},
    {"x": 0, "y": 1, "z": 0, "role": "WALL"}
  ]
}
```

约束：

- 无随机数。
- 相同 Spec 必须输出相同 blocks（数量与坐标一致）。
- 不做材质映射，不做执行。

---

## 5) Material Alias 映射协议

输入：`material_preference + role`  
输出：合法 MC block id

示例：

```json
{
  "wood": {
    "FLOOR": "oak_planks",
    "WALL": "oak_planks",
    "ROOF": "oak_slab"
  },
  "stone": {
    "FLOOR": "stone",
    "WALL": "stone_bricks",
    "ROOF": "stone_slab"
  },
  "brick": {
    "FLOOR": "bricks",
    "WALL": "bricks",
    "ROOF": "brick_slab"
  }
}
```

规则：

- 白名单外映射直接 `raise`。
- 不存在映射直接 `REJECTED`，不得 fallback。

---

## 6) 执行层协议（禁止隐式回退）

执行层只接收：

```json
{
  "blocks": [
    {"x": 1, "y": 64, "z": 1, "block": "oak_planks"}
  ]
}
```

禁止行为：

- 禁止默认 `shape=platform`。
- 禁止默认 `material=OAK_PLANKS`。
- 非法 block id 直接拒绝并记录 failure_code。

返回建议：

```json
{
  "build_status": "SUCCESS | REJECTED",
  "failure_code": "NONE | INVALID_BLOCK_ID | OUT_OF_BOUNDS | EMPTY_BLOCKS"
}
```

---

## 7) 可观测性（最小埋点）

每轮生成必须记录：

- `build_id`
- `spec_status`
- `build_status`
- `failure_code`
- `build_path`（固定值：`spec_engine_v1`）
- `patch_source`（固定值：`deterministic_engine`）

这 6 个字段应进入 debug 面板，用于统计与回放。

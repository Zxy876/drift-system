# Copilot Issues：Deterministic Generation 落地拆解

## Issue 1：实现 Spec Validator（v1）

### 目标

新增 `spec_validator.py`，用于校验 LLM 语义 Spec，拒绝执行层字段。

### 范围

- 输入：Spec JSON。
- 输出：`status + failure_code + message + normalized_spec`。
- 支持 failure_code：
  - `MISSING_FIELD`
  - `INVALID_ENUM`
  - `OUT_OF_RANGE`
  - `FORBIDDEN_EXEC_FIELD`

### 验收标准

- 对合法 Spec 返回 `VALID`。
- 对缺字段/非法枚举/越界返回 `REJECTED`。
- 出现 `blocks/build/mc/world_patch` 字段必须 REJECTED。
- 单元测试覆盖上述四类 failure_code。

---

## Issue 2：实现 Deterministic Build Engine

### 目标

新增 `deterministic_build_engine.py`，只做几何生成。

### 范围

- 输入：已验证 Spec。
- 输出：抽象 `blocks`（role + 相对坐标）。
- 首批支持：`house/tower/wall/bridge`。
- 禁止随机、禁止 fallback。

### 验收标准

- 相同 Spec 多次运行，输出 blocks 完全一致。
- 不支持结构返回 `REJECTED + UNSUPPORTED_STRUCTURE`。
- 增加测试：`7x5 house` 的 block 总数固定且可断言。

---

## Issue 3：实现 Material Alias Mapper + 执行层禁 fallback

### 目标

新增 `material_alias_mapper.py` 并改造执行入口，移除隐式默认 shape/material。

### 范围

- Mapper 输入：`material_preference + role`。
- Mapper 输出：白名单 MC block id。
- 无映射直接抛错，不做默认替代。
- 执行层仅接受 `blocks`，非法 block id 直接 REJECTED。

### 验收标准

- 不再出现默认 `platform/OAK_PLANKS` 静默回退。
- 响应统一包含：
  - `build_status: SUCCESS | REJECTED`
  - `failure_code`
  - `build_path: spec_engine_v1`
  - `patch_source: deterministic_engine`
- debug 面板可见以上字段并可统计。

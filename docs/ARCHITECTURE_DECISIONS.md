# DriftSystem 架构决策记录（ADR）

> 更新时间：2026-03-07
> 状态说明：`Accepted` = 已采纳并作为后续实现约束。

---

## ADR-001：Planner / Executor 双端分工

- 状态：Accepted
- 日期：2026-03-07

### 背景

DriftSystem 当前链路已形成：

`Backend Planner -> world_patch JSON -> Plugin Executor -> Minecraft World`

若将 AI 推理与世界执行放在同一端，会出现以下问题：

- 全后端生成：payload 体积与网络开销过大
- 全插件生成：Java 侧推理复杂度、调试成本与稳定性风险提升

### 决策

采用 `C` 模式（planner + executor）：

- Backend 负责：semantic reasoning、scene graph、layout、event_plan、world_patch planning
- Plugin 负责：`build_multi / structure / blocks / spawn` 的最终世界执行

### 影响

- 维持跨层职责清晰，避免逻辑漂移
- world_patch 成为唯一跨端契约
- 有利于后续 P9 资产扩展与观测审计

---

## ADR-002：Asset Registry 先于 Narrative Decision

- 状态：Accepted
- 日期：2026-03-07

### 背景

P8-B `choose_transition` 若先于 P9-A，叙事决策仅能看到旧片段集合（如 camp/village/forge），无法感知新资产（mod/poetry/theme pack）。

### 决策

将执行顺序调整为：

`P9-A Asset Registry -> P8-B Narrative Decision -> P9-B/P9-C/...`

并要求 Narrative Decision 输入资产可见性（asset/theme filter）。

### 影响

- 叙事决策与资产可执行性保持一致
- 避免“可选转场存在但无可执行资产”
- 支撑 asset-aware transition 的可观测实现

---

## ADR-003：Deterministic Scene Graph 为硬约束

- 状态：Accepted
- 日期：2026-03-07

### 背景

DriftSystem 需长期支持 replay、debug、回归验证与多人服务端稳定性。非确定性生成会破坏这些能力。

### 决策

将以下规则设为硬约束：

- same input -> same semantic result
- same semantic/theme/assets -> same scene graph/event_plan/world_patch
- Runtime probe 与回归测试需持续验证 deterministic

### 影响

- 保证 P6–P9 可持续演进
- 降低线上排障复杂度
- 为 Asset Compiler 与 Narrative Decision 提供稳定基线

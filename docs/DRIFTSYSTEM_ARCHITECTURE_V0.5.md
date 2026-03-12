# DriftSystem Architecture v0.5（Frozen）

日期：2026-03-05  
状态：Frozen（首次稳定闭环）

---

## 1) 架构冻结目标

- 本版本不再讨论“是否打通”，而是冻结“已打通的最小闭环”。
- 冻结范围限定为三层：`TRNG Layer`、`Scene Layer`、`World Layer`。
- 后续迭代只允许在冻结边界内做增量，不允许跨层混改。

---

## 2) 三层架构（Control View）

```mermaid
flowchart TD
  P[玩家行为 / NL / 交互] --> RE[RuleEvent Ingress]
  RE --> TX[TRNG Layer\nbegin/apply/commit]
  TX --> SI[/story/inject]
  SI --> SC[Scene Layer\nfragments + event_plan]
  SC --> WP[World Patch Compose]
  WP --> EX[World Layer\nWorldPatchExecutor]
  EX --> AR[/world/apply/report]
  AR --> WS[state update]
```

闭环定义：

`RuleEvent -> Transaction -> Scene Plan -> World Patch -> Executor -> Apply Report -> State`

---

## 3) Layer 1: TRNG Layer

### 职责
- 管理事务生命周期：`begin_tx -> apply_event -> commit/rollback`。
- 保证 draft 与 committed 隔离，确保原子发布。
- 输出可追踪事务收据（hash、event_count、tx_id）。

### 输入
- 标准化交互事件（talk/trigger/collect 等）。
- 当前 committed graph/state。

### 输出
- committed graph/state（成功时）。
- transaction receipt（包含 `tx_id`、state/graph hash、rule_version）。

### 冻结约束
- 不在 TRNG 层直接生成 MC 结构。
- 不在 TRNG 层耦合插件执行细节。

---

## 4) Layer 2: Scene Layer

### 职责
- 基于 `inventory + scene_theme + scene_hint + anchor` 生成：
  - `scene_plan`（fragments）
  - `event_plan`（可执行场景事件序列）
- 保持确定性（同输入同输出）。

### 输入
- 来自 TRNG/Runtime 的状态切片。
- 玩家主题/提示词（`scene_theme`、`scene_hint`）。

### 输出
- `spawn_camp / spawn_fire / spawn_npc / spawn_cooking_area` 等场景事件。
- 供 World Layer 消费的 patch 语义（structure/build/spawn/blocks）。

### 冻结约束
- Scene 层不直接执行世界修改。
- Scene 层不决定 executor 运行时策略。

---

## 5) Layer 3: World Layer

### 职责
- 将 event_plan/world_patch 执行到 Minecraft 世界。
- 回传 apply 执行结果（`/world/apply/report`）。
- 承担协议兼容与执行容错（含 `offset` 语义支持）。

### 输入
- `bootstrap_patch.mc` / `scene_world_patch.mc`。

### 输出
- 世界变化（结构、方块、实体、天气、提示等）。
- apply report（executed/failed/status/failure_code）。

### 冻结约束
- Executor 不反向修改 TRNG 事务语义。
- Executor 不重写 Scene 规则，仅负责正确执行。

---

## 6) 层间契约（Frozen Contracts）

### C1: RuleEvent Contract
- 入口：`/world/story/rule-event`
- 语义：统一事件封装，允许 debug 下附带事务摘要。

### C2: Scene Contract
- 入口：`/story/inject`
- 输出至少包含：`scene_plan`、`event_plan`、可选 `scene_world_patch`。

### C3: World Contract
- 入口：`/story/load`（下发 patch）与 `/world/apply/report`（回传执行）。
- `offset` 为一等语义，必须可执行，禁止静默丢弃。

---

## 7) 当前里程碑判定（v0.5）

- 闭环已成立：
  - `event_to_transaction = true`
  - `inject_transaction = true`
  - `transaction_to_world_patch = true`
  - `world_patch_to_minecraft_load = true`
  - `minecraft_to_state_update = true`
- `last_apply_report` 可观测为 `EXECUTED` 且 `failed = 0`。
- 先前“看不到营地/NPC”根因已确认并修复：`offset` 执行兼容。

---

## 8) v0.5 后唯一优先队列（按顺序）

### P1（最高）: Safe Ground Anchor
- 目标：场景落地到可见地面，避免海面/空中落点。
- 规则：player anchor -> downward probe -> first solid block。

### P2: Inventory Canonical Mapping
- 目标：MC item 统一到 canonical resource（如 `oak_log -> wood`）。
- 作用：稳定 SceneAssembler 触发条件。

### P3: NPC Behavior RuleEvents
- 目标：把对话/攻击/点火纳入规则事件链并进入 TRNG。
- 作用：从“可生成场景”升级为“可交互叙事沙盒”。

---

## 9) 非目标（本冻结版本不做）

- 不重构 TRNG 核心事务语义。
- 不重写 Scene 模板系统为生成式。
- 不在本版本扩展多世界复杂调度。

---

## 10) 变更守则（执行）

- 任意改动必须标注归属层（TRNG/Scene/World）。
- 禁止“为了修一层问题改另一层语义”。
- 每次发版至少保留一次端到端闭环探针证据。

> 该文档作为 DriftSystem 第一版稳定架构基线；后续进入 v0.6 时，仅允许在本冻结边界上演进。

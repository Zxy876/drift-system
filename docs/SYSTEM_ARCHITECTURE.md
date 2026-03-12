# DriftSystem 系统架构（P8-B / P9-A 基线）

DriftSystem is a deterministic AI-driven narrative world engine that composes Minecraft scenes from semantic resources and narrative transitions.

> 更新时间：2026-03-07  
> 基线标签：`p9a-baseline`、`p8b-decision`

## 1. 一图看懂

```mermaid
flowchart TD
    A[Player Event] --> B[RuleEventBridge]
    B --> C[Semantic Layer]
    C --> D[Asset Layer]
    D --> E[Scene Layer]
    E --> F[Narrative Layer]
    F --> G[world_patch Contract]
    G --> H[Minecraft Plugin Executor]
    H --> I[Minecraft World]

    C1[semantic tags / scoring] --> C
    D1[asset registry] --> D
    E1[scene graph / scene evolution] --> E
    F1[narrative graph / choose_transition] --> F

    O1[/world/state] -.observe.-> C
    O1 -.observe.-> D
    O1 -.observe.-> E
    O1 -.observe.-> F
    O2[/world/story/{player}/debug/tasks] -.observe.-> C
    O2 -.observe.-> D
    O2 -.observe.-> E
    O2 -.observe.-> F
```

  ## 1.1 Data Flow Diagram

  ```mermaid
  flowchart TD
    A[player action] --> B[rule_event]
    B --> C[semantic engine]
    C --> D[asset registry]
    D --> E[scene assembler]
    E --> F[narrative decision]
    F --> G[world_patch]
    G --> H[minecraft]
  ```

## 2. 分层职责

### Semantic Layer（语义层）

- 输入：inventory/resources、rule events。
- 输出：语义信号（如 `scene:*`、`collect:*`、`event:*`、`level_stage:*`）。
- 目标：把原始资源转换为可解释的语义空间。

### Asset Layer（资产层）

- 核心：`asset_registry`（含 `type/source/semantic_tags/spawn_method`）。
- 作用：统一 vanilla/mod/pack 等资产来源，向 scene 选择与 narrative 决策提供可见资产集合。
- 约束：注册表是单一事实来源，避免多套资产来源并行漂移。

### Scene Layer（场景层）

- 核心：`scene_library`、`scene_graph`、`scene_evolution`、`layout_engine`。
- 输出：可执行 `event_plan` 与可追踪 `scene_state/scene_diff`。
- 目标：从语义和资产映射到可稳定生成的场景结构。

### Narrative Layer（叙事层）

- P8-A：`transition_candidates` 只读评估。
- P8-B：显式 `choose_transition` 决策、`narrative_policy` 评分、`narrative_transition` 审计日志。
- 约束：
  - 不自动推进（必须显式 API 调用）。
  - 不直接触发 world patch（只更新 narrative state / transition log）。

### Execution Layer（执行层）

- 契约：`world_patch`。
- 执行：Minecraft 插件负责最终 world build/spawn/block 变更。
- 架构关系：Backend Planner 与 Plugin Executor 职责分离（参见 ADR）。

## 3. 核心接口（当前）

- `GET /world/state/{player_id}`：聚合 world + narrative + asset observability。
- `GET /world/story/{player_id}/debug/tasks`：运行态调试与可观测快照（对应 `/eventdebug`）。
- `POST /world/story/{player_id}/spawnfragment`：显式触发 scene fragment 生成。
- `POST /world/story/{player_id}/narrative/choose`：显式叙事决策（P8-B）。
- `POST /world/story/rule-event`：规则事件入口（驱动 scene/narrative 输入侧）。

## 4. 系统硬约束

- Deterministic：相同输入得到相同决策与输出。
- Observable：关键链路字段在 state/debug 接口可见。
- Auditable：每次 narrative transition 可追踪、可回放。
- Decoupled：Narrative Decision 与 World Patch 解耦，保持层边界清晰。

## 5. 当前里程碑映射

- P7.2：Scene Evolution（增量扩图 + 增量 patch）。
- P8-A：Narrative Skeleton（候选转场可观测）。
- P9-A：Asset Registry（统一资产层）。
- P8-B：Narrative Decision（显式、deterministic、可审计）。

## 6. 下一步建议（最小范围）

- P9-B Semantic Adapter：
  - 建立 mod/custom item 到语义标签的统一适配入口；
  - 输出仍汇入现有语义信号体系，不改变 scene/narrative 契约。

## 7. 相关文档

- `docs/DRIFTSYSTEM_ROADMAP.md`
- `docs/ARCHITECTURE_DECISIONS.md`

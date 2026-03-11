# DriftSystem Intent Engine 审计报告

- 日期：2026-03-11
- 范围：`drift-backend` + `drift-plugin`（含 `drift-web` 的 Poetry 前端调用）
- 目标：厘清当前“聊天 -> 意图 -> 世界执行”链路，评估 Poetry 功能应走独立系统（Route A）还是并入 Intent Engine（Route B）。

## 1) 现状总览（结论先行）

当前线上实际上有**并行的两条聊天处理链路**：

1. `RuleEventBridge` 链：插件把聊天作为规则事件发送到后端 `/world/story/rule-event`，后端返回 `world_patch/nodes/commands`，插件立即执行。
2. `IntentRouter2` 链：插件同一条聊天再发到后端 `/ai/intent`，得到 `intents[]` 后由 `IntentDispatcher2` 分发执行。

这导致同一输入可能被“双重处理”，是当前架构最重要的耦合点。

### 状态更新（2026-03-11）

- `PlayerChatListener` 已收敛为单通道：仅走 `IntentRouter2 -> /ai/intent -> IntentDispatcher2`。
- `NearbyNPCListener` 已做半步收敛：
  - NPC 对话语义改为走 `IntentRouter2 + IntentDispatcher2`；
  - `near / interact / trigger` 等游戏事件仍走 `RuleEventBridge`。
- `/talk` 命令已单通道化：命令内部复用聊天入口（`p.chat(msg)`），最终走 `PlayerChatListener -> IntentRouter2 -> IntentDispatcher2`。
- 结论：当前系统形态为 **Dual Engine Architecture（Intent + Narrative）**，而非纯单引擎。

## 2) 运行时架构图

```mermaid
flowchart LR
    A[Player Chat] --> B[PlayerChatListener]

    B --> C[RuleEventBridge]
    C --> D[/world/story/rule-event]
    D --> E[quest_runtime + scene bridge + parse_intent(summary)]
    E --> F[world_patch / nodes / commands]
    F --> G[RuleEventBridge.applyRuleEventResult]
    G --> H[WorldPatchExecutor + HUD/Dialogue]

    B --> I[IntentRouter2]
    I --> J[/ai/intent]
    J --> K[intents[]]
    K --> L[IntentDispatcher2]
    L --> M[/story/inject /story/load /world/apply / local world.execute]

    N[/talk command] --> O[TalkCommand]
    O --> C
    O --> P[Legacy IntentRouter]
    P --> Q[/story/advance]
```

## 3) 现有意图清单与对齐情况

### 3.1 后端 `intent_engine` 声明的意图

- `CREATE_STORY`
- `SHOW_MINIMAP`
- `SET_DAY`
- `SET_NIGHT`
- `SET_WEATHER`
- `TELEPORT`
- `SPAWN_ENTITY`
- `BUILD_STRUCTURE`
- `GOTO_LEVEL`
- `GOTO_NEXT_LEVEL`
- `STORY_CONTINUE`
- `SAY_ONLY`

### 3.2 插件 `IntentType2` 支持的意图

- 与上面基本一致，并额外有 `UNKNOWN`。

### 3.3 缺口

- **没有 Poetry 专用意图类型**（例如 `CREATE_POETRY_SCENE` / `POETRY_SCENE`）。
- `/poetry/command` 已在后端可用，但不在统一意图分类体系里。
- 插件 `plugin.yml` 当前没有 `/poem` 命令注册。

## 4) 已有 Poetry 能力与可复用基础

### 4.1 后端

- `POST /poetry/generate`：诗歌 -> 概念/语义 -> 资源映射 -> 场景事件 -> `world_patch`。
- `POST /poetry/command`：兼容插件命令文本（`/poem ...`）并返回 `mc_actions` 摘要。
- `poetry_engine.py` 已实现：
  - 诗歌概念抽取
  - 语义融合
  - 玩家隐喻备案（`registry/player-tags`）加权
  - 主题建议与默认 hint

### 4.2 插件

- `WorldPatchExecutor` 已支持 Poetry 常见动作键：`build_multi`、`spawn_multi`、`blocks`、`structure`。
- 说明执行器能力已具备，瓶颈主要在“路由与意图统一”，不是执行层。

## 5) 关键发现（审计结论）

1. **双通道并行是当前主要复杂度来源**
   - 聊天同时走 `/world/story/rule-event` 与 `/ai/intent`，潜在重复执行、重复状态推进。

2. **`/world/story/rule-event` 已内置意图解析，但只用作摘要/场景桥接信息**
   - 后端会对 talk 文本做 `parse_intent`，但该结果目前并未成为统一的“动作分发中心”。

3. **Poetry 已有独立 API 能跑通，但尚未纳入统一 Intent Taxonomy**
   - 这正是 Route A 与 Route B 的分歧点。

4. **插件仍保留 Legacy `IntentRouter` 路径**
   - `/talk` 与邻近 NPC 路径仍可走旧接口，增加架构分叉。

## 6) Route A vs Route B 评估

### Route A：Poetry 保持独立（命令直连 `/poetry/command`）

**优点**
- 改动小、上线快。
- 不影响现有 Intent 语义。

**缺点**
- Poetry 成为旁路，不纳入统一意图观测、统计和策略。
- 长期维护成本上升（调试、埋点、权限、策略会分叉）。

### Route B：Poetry 并入 Intent Engine（推荐）

**优点**
- 自然语言入口统一（聊天/命令最终归入同一意图体系）。
- 可复用现有规则事件与观测链路。
- 后续扩展（权限、风控、策略门控）更一致。

**缺点**
- 需要处理中短期兼容（双通道并行、旧路由保留）。

## 7) 推荐方案（建议采用 Route B，分阶段落地）

### Phase 0：兼容保护

- 增加开关：`DRIFT_INTENT_POETRY_ENABLED=true/false`。
- 保留 `/poetry/command` 作为回退与调试通道。

### Phase 1：后端意图层并入 Poetry

- 在 `app/core/ai/intent_engine.py`：
  - 新增意图类型：`CREATE_POETRY_SCENE`（或 `POETRY_SCENE`）。
  - 规则/提示词支持 `/poem ...`、`写诗场景`、`把这首诗变成场景` 等表达。

### Phase 2：规则事件链路执行 Poetry

- 在 `app/api/world_api.py::story_rule_event`：
  - 当 `intent.type == CREATE_POETRY_SCENE` 时，调用 Poetry 生成逻辑并合并到 `result.world_patch`。
  - 与现有 `talk_scene_bridge` 合并时，明确优先级（建议 Poetry patch 优先，普通 talk bridge 作为补充或跳过）。

### Phase 3：插件收敛入口

- 新增 `/poem` 命令（`plugin.yml` + 命令执行器）。
- `/poem` 命令应复用统一聊天/规则事件入口，而非新增第三条专线。
- 在过渡期可对 `PlayerChatListener` 加保护：对 `/poem` 前缀避免双通道重复处理。

### Phase 4：观测与回归

- 在 `story_rule_event` 返回中补充：`intent.type`、`poetry_applied`、`mc_action_counts`。
- 回归重点：
  - 普通聊天推进不受影响
  - `/poem` 能稳定产出 `world_patch.mc.build_multi`
  - 不发生重复执行/重复刷怪/重复建造

## 8) 具体改造落点（文件级）

### backend

- `app/core/ai/intent_engine.py`（意图类型、fallback、prompt）
- `app/api/world_api.py`（`story_rule_event` 内 Poetry 分发与 patch 合并）
- `app/api/poetry_api.py`（建议抽公共 service，避免 API 层函数硬耦合）
- `test_intent_event_api.py`（新增 Poetry 意图回归用例）

### plugin

- `src/main/resources/plugin.yml`（注册 `/poem`）
- `src/main/java/com/driftmc/DriftPlugin.java`（注册命令执行器）
- `src/main/java/com/driftmc/listeners/PlayerChatListener.java`（过渡期防双处理）
- `src/main/java/com/driftmc/intent2/IntentType2.java`（新增 Poetry intent 枚举，若由 `/ai/intent` 使用）
- `src/main/java/com/driftmc/intent2/IntentDispatcher2.java`（Poetry intent 分发策略）

## 9) 最终建议

从系统演进角度，**应选择 Route B（并入 Intent Engine）**，并保留 `/poetry/command` 作为兼容兜底。

这能在不推翻现有功能的前提下，逐步把 Poetry 从“独立特性”升级为“统一意图体系的一等能力”。

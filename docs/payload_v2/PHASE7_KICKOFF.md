# Phase 7 Kickoff（Narrative Scene System）

日期：2026-03-05  
状态：Kickoff

## Scene Assembler
- 目标：把 `InventoryState + StoryTheme` 组合为可执行的场景计划。
- 输入：
  - `inventory_state`（玩家资源快照）
  - `story_theme`（诗歌/文本主题）
  - `scene_hint`（可选场景提示，例如：森林/海边）
  - `anchor_position`（场景锚点，默认玩家位置）
- 输出：
  - `scene_plan`（场景结构：地点、NPC、交互点）
  - `event_plan`（事务事件序列）
- 约束：
  - 仅做“叙事拼贴层”，不改 `runtime/TRNG/plugin`。
  - 第一版使用规则驱动（非生成式）以保证可控与可回放。

## Inventory State
- Phase7 使用统一资源视图（来自 Phase6 collect 行为累积）：
  - `player_id: str`
  - `resources: dict[str, int]`（示例：`wood`, `torch`, `pork`）
  - `updated_at_ms: int`
- 读取原则：
  - 只读输入给 Scene Assembler。
  - 不在 Phase7 直接写底层 runtime state。
- MVP 资源键（首批）：
  - `wood`
  - `torch`
  - `pork`

## Scene Hint（可选）
- 目标：在不改 runtime/TRNG 语义的前提下，携带额外场景上下文。
- 示例：
  - “创建剧情 大风吹 在森林里” -> `scene_theme=大风吹`, `scene_hint=森林`
  - “创建剧情 暴风雨 在海边” -> `scene_theme=暴风雨`, `scene_hint=海边`
- 说明：Kickoff 阶段先作为 SceneAssembler 输入与事件元数据透传，后续版本可扩展为更强模板分支选择。

## Scene Template
- 第一版模板采用规则映射（Rule-driven）：

| Resource / Theme Signal | Scene Template Fragment |
|---|---|
| `wood >= 1` | `camp`（营地） |
| `torch >= 1` | `fire`（篝火） |
| `pork >= 1` | `cooking_area`（烹饪点） |
| 主题含“荒野/风” | `wanderer_npc`（流浪 NPC） |

- 模板输出不直接落世界；先转 `event_plan`，再走事务提交。
- 后续可扩展为多模板拼接，但 Kickoff 仅允许单模板/少量组合。

## Event Plan
- `event_plan` 是进入 TRNG 的标准事件列表（按顺序执行）：
  - `spawn_camp`
  - `spawn_fire`
  - `spawn_npc`
  - `spawn_cooking_area`
- 事件结构（建议）：
  - `event_id`
  - `type`
  - `text`
  - `anchor`
  - `data`
- 执行路径（冻结）：
  - `SceneAssembler -> EventPlan -> run_transaction(events) -> runtime -> world_patch`

---

## Phase7 MVP 边界（冻结）
- 允许：
  - 新增 `scene_assembler` 及模板数据。
  - 新增“资源+主题 -> 事件计划”规则。
- 禁止：
  - 修改 Phase4 runtime 语义。
  - 修改 Phase5 TRNG 事务语义。
  - 修改 Phase6 插件监听与桥接协议。

## Phase7 MVP 完成定义
- 输入同一 `inventory_state + story_theme` 时，输出同一 `event_plan`（确定性）。
- `event_plan` 可被事务层提交并产出 `world_patch`。
- 至少支持一个可见场景链路：`wood + torch + pork -> camp/fire/cooking + npc`。

# Drift-Web Blueprint v1

## 1. 文档状态

- 版本：v1.2（执行蓝图，已对齐当前实现）
- 日期：2026-03-10
- 适用范围：Drift-Web 产品化阶段（Runtime Observatory + Creator Console）
- 目标：冻结讨论，进入可执行开发阶段

---

## 2. 事实基线（已确认）

| 层 | 规模 | 状态 |
|---|---:|---|
| Narrative Graph | 3 nodes | MVP |
| Level Graph | 3 levels | MVP |
| Scene Library | 50 fragments（47 builtin + 3 pack） | 已成熟 |
| Semantic Tags | 83 entries | 已成熟 |
| Themes | 6 | 已成熟 |
| Backend | ~32k LOC | 系统级 |
| REST API | 可用且覆盖状态观察/部分操作 | 可供 Web 使用 |

> 结论：当前 Drift 是“小叙事图 + 大场景库 + 语义系统”的典型 AI 叙事引擎形态。

---

## 3. v1 产品定位

Drift-Web v1 当前定位为：

**Narrative Runtime Observatory（Creator Console）**

核心职责：

- 观察（Observe）：运行态状态、叙事流、场景选择与补丁结果可视化
- 解释（Explain）：自然语言输入如何映射到 intent / semantic / narrative / scene / world
- 控制（Control）：控制场景生成节奏与触发策略（Generation Control）

非目标：

- 不做内容编辑器（Graph Editor/Content IDE 放在后续版本）
- 不重写引擎生成逻辑（后端仍为 source-of-truth）

---

## 4. 系统边界

### 4.1 控制/执行平面

```text
Browser
  ↓
Drift-Web (Next.js/React)
  ↓
Drift Backend API
  ↓
Drift Engine Runtime
  ↓
Minecraft Plugin
```

### 4.2 v1 只做

- 观察（state/debug 可视化）
- 配置（玩家语义备案、场景/资源配置）
- 调用已有 API（意图解析、场景预览、叙事选择）

### 4.3 v1 不做

- 不重写生成逻辑（scene generation / world patch 仍由后端引擎执行）
- 不做复杂关卡编辑器（拖拽式大规模 Graph Editor 放在后续）
- 不直接控制 Minecraft 执行层

---

## 5. 信息架构（IA）

```text
Drift Web
│
├── Runtime
│   ├── /player/[playerId]
│   └── /intent/[playerId]
│
├── Narrative
│   └── /narrative/[playerId]
│
├── Content
│   └── /scenes
│
├── Control
│   ├── /settings/generation
│   └── /registry
│
└── System
  └── /about
```

### 5.1 当前仓库已落地模块（2026-03-10）

| Route | 模块 | 状态 |
|---|---|---|
| `/player/[playerId]` | Player Dashboard | 已实现 |
| `/narrative/[playerId]` | Narrative Map | 已实现 |
| `/intent/[playerId]` | Intent Debugger（含 Command Observatory v1） | 已实现 |
| `/scenes` | Scene Explorer | 已实现 |
| `/about` | Architecture / Positioning | 已实现 |
| `/settings/generation` | Generation Control（运行时门控） | 已实现 |
| `/registry` | Resource Registry（玩家语义配置） | 已实现（v1 基础骨架） |

---

## 6. 模块蓝图

## 6.1 Player Console

### 页面 A：Player Dashboard

- 数据源：`GET /world/state/{player_id}`
- 展示：
  - current node
  - quest / active tasks
  - emotion weather
  - world snapshot
  - recommendations

### 页面 B：Intent Inspector

- 数据源：`POST /ai/intent`
- 展示：
  - intents 列表
  - scene_theme / scene_hint
  - 解释“AI 为什么这样解析”

### 页面 C：Scene Preview

- 数据源：`POST /world/story/{player_id}/spawnfragment`
- 展示：
  - scene
  - world_patch
  - fragment_count / event_count

---

## 6.2 Narrative Debugger（v1 核心）

### 页面 A：Narrative Map

- 主图：基于 narrative graph（当前 3 节点）+ 玩家 current node 高亮
- 运行态叠加：
  - `current_node`
  - `transition_candidates`
  - `blocked_by`

### 页面 B：Narrative State Panel

- 数据源：`GET /world/state/{player_id}`
- 展示：
  - narrative_state
  - memory flags（若可见）
  - task conditions（来自任务快照）

### 页面 C：Scene Evolution

- 数据源：`GET /world/state/{player_id}` + Debug 端点
- 展示：最近 scene generation / scene_diff（若可见）

---

## 6.3 Resource Registry（玩家资源备案）

目标：解决 semantic gap（玩家词汇 ↔ Minecraft 资源）

### 页面 A：Search Resource

- 输入关键词（例：神社）
- 调用外部资源索引（见第 9 节）
- 返回可候选资源（id、名称、类型、图示/链接）

### 页面 B：My Tags

- 玩家备案：`tag -> resource_id`
- 支持新增/删除/查看

### 页面 C：Scene Templates（可选）

- 保存玩家偏好的场景模板：theme/resources/anchor

---

## 6.4 Scene Explorer（只读优先）

### 页面：Scene Library

- 数据来源：
  - `GET /scenes/library`（后端聚合）
- 展示：
  - fragment roots/children
  - themes 与 allowed fragments
  - semantic tags 映射

> 约束：前端不直接读取仓库文件路径，避免部署路径耦合。

---

## 6.5 Admin / Debug

### 页面 A：Player Monitor

- 按 player_id 查询状态
- 聚合 story/world/quest/narrative 数据

### 页面 B：Transaction Debug（预留）

- 展示事务相关 debug 字段（若后端返回）
- 为后续 TRNG ledger 做 UI 预留

---

## 7. API Contract（v1）

## 7.1 直接使用（已存在）

| Method | Path | 用途 |
|---|---|---|
| GET | `/world/state/{player_id}` | 玩家综合状态、叙事状态 |
| POST | `/ai/intent` | 意图解析检查 |
| POST | `/world/story/{player_id}/spawnfragment` | 场景预览 |
| POST | `/world/story/{player_id}/narrative/choose` | 叙事分支选择 |
| GET | `/world/story/{player_id}/quest-log` | 任务日志 |
| GET | `/world/story/{player_id}/memory` | 记忆标记 |
| GET | `/world/story/{player_id}/recommendations` | 推荐剧情 |
| GET | `/world/story/{player_id}/debug/tasks` | 调试快照（受 token 控制） |

## 7.2 v1 需新增（Resource Registry）

| Method | Path | 请求 | 响应 |
|---|---|---|---|
| POST | `/registry/player-tags` | `{ player_id, tag, resource_id, resource_type?, namespace?, source? }` | `{ status, item }` |
| GET | `/registry/player-tags/{player_id}` | - | `{ status, items[] }` |
| DELETE | `/registry/player-tags/{id}` | - | `{ status, deleted }` |
| GET | `/registry/resources/search?q=...` | query: `q, limit?, source?` | `{ status, query, items[] }` |

## 7.3 v1 需新增（Generation Policy）

| Method | Path | 用途 |
|---|---|---|
| GET | `/settings/generation` | 读取当前场景生成策略 |
| POST | `/settings/generation` | 更新场景生成策略 |

建议返回结构：

```json
{
  "scene_cooldown": 60,
  "spawn_probability": 0.4,
  "max_scenes_per_hour": 5,
  "spawn_distance": 40,
  "require_player_movement": true,
  "require_new_location": true
}
```

字段说明：

- `scene_cooldown`：两次生成的最小时间间隔
- `spawn_probability`：候选生成触发概率（0~1）
- `max_scenes_per_hour`：每小时最大生成次数
- `spawn_distance`：距离上次生成点的最小距离阈值
- `require_player_movement`：要求玩家有位移才允许生成
- `require_new_location`：要求进入新区域/新位置才允许生成

运行时观测（由 `/world/state/{player_id}` 与 `/world/story/{player_id}/debug/tasks` 暴露）：

- `generation_policy_gate`：本次门控结果（`allowed/reason/next_available_in`）
- `generation_skipped` / `generation_skip_reason`：是否跳过及原因
- `scenes_generated_last_hour`：最近 1 小时生成数
- `scenes_blocked_by_policy`：累计被门控拦截次数
- `policy_block_rate`：门控拦截率（`0~1`）
- `avg_scene_interval`：平均场景生成间隔（秒）
- `policy_cooldown_hits`：冷却窗口命中次数（累计）

## 7.4 v1 需新增（Scene / Narrative）

| Method | Path | 用途 |
|---|---|---|
| GET | `/scenes/library` | Scene Explorer 聚合数据源 |
| GET | `/narrative/graph` | Narrative Map 图结构数据 |

`GET /narrative/graph` 建议响应 schema：

```json
{
  "status": "ok",
  "graph_version": "p8a_v1",
  "entry_node": "forest_intro",
  "nodes": [
    {
      "id": "forest_intro",
      "type": "entry",
      "arc": "main",
      "requires": [],
      "next": ["village_meeting"]
    }
  ],
  "edges": [
    {
      "from": "forest_intro",
      "to": "village_meeting"
    }
  ]
}
```

稳定字段要求（前端依赖）：

- `nodes[].id`
- `edges[].from`
- `edges[].to`

可选增强字段：

- `nodes[].type`
- `nodes[].arc`
- `nodes[].requires`
- `nodes[].next`

> 注：v1 以“后端聚合 API”为前提，前端不直接访问仓库文件。

## 7.5 v2/v3 预留接口

| Method | Path | 用途 |
|---|---|---|
| GET | `/admin/narrative-graph` | 读取 narrative_graph source-of-truth |
| POST | `/admin/narrative-graph` | 保存并触发 reload |

---

## 8. 数据模型（v1）

## 8.1 player_tags

```sql
id            INTEGER PRIMARY KEY AUTOINCREMENT
player_id     TEXT NOT NULL
tag           TEXT NOT NULL
resource_id   TEXT NOT NULL
resource_type TEXT NOT NULL
namespace     TEXT NOT NULL
source        TEXT NULL
created_at    INTEGER NOT NULL
updated_at    INTEGER NOT NULL
UNIQUE(player_id, tag)
```

## 8.2 API DTO

```json
{
  "id": 12,
  "player_id": "vivn",
  "tag": "神社",
  "resource_id": "minecraft:jungle_temple",
  "resource_type": "structure",
  "namespace": "minecraft",
  "source": "misode",
  "created_at": 1710000000000,
  "updated_at": 1710000000000
}
```

---

## 9. 外部资源源（Resource Search）

优先级建议：

1. **PrismarineJS/minecraft-data**（结构化、可本地索引）
2. **Misode mcmeta**（JSON 化资源元数据）
3. **Minecraft Wiki API**（图片/描述增强）

v1 策略：

- 先做“本地缓存索引 + 搜索”，避免运行时频繁外呼。
- 对外部资源源统一走后端 Proxy（`/registry/resources/search`），前端不直连第三方。
- 外部源只做候选推荐，不直接写 semantic_registry 主表。
- 玩家选择后写入 `player_tags`，由后端语义解析层优先合并。

---

## 10. 技术栈与实现建议（前端）

- Next.js（App Router）
- React + TypeScript
- Tailwind
- React Flow（Narrative Map）

建议路由：

- `/player/[playerId]`
- `/intent/[playerId]`
- `/narrative/[playerId]`
- `/scenes`
- `/settings/generation`
- `/registry`
- `/about`

---

## 11. 分期计划

## Phase 1（1–2 周）

- Player Console（Dashboard）
- Narrative Debugger（Narrative Map）
- Scene Explorer（只读）
- Intent Debugger（解释链路 v1）
- 全部走现有只读/半写 API

验收：玩家可读懂“当前剧情在哪、为什么触发了这个结果”。

## Phase 2

- Generation Control（`/settings/generation`）+ Runtime Gate
  - `scene_cooldown`
  - `spawn_probability`
  - `max_scenes_per_hour`
  - `spawn_distance`
  - `require_player_movement`
  - `require_new_location`
  - `generation_policy_gate` 观测链路
  - `scenes_generated_last_hour / scenes_blocked_by_policy / policy_block_rate`
  - `avg_scene_interval / policy_cooldown_hits`

验收：剧情节奏可控，且可解释“为什么生成/为什么被跳过”。

## Phase 3

- Resource Registry 三接口
- `/registry` 页面与备案闭环

验收：玩家可完成“搜索资源 → 备案 tag → 生效查询”。

## Phase 4

- Narrative Graph Editor（结构编辑，IDE 能力）
- `/admin/narrative-graph` 读写接口

验收：可在 Web 修改 graph 并 reload 生效。

---

## 12. 验收标准（v1 Done）

- 可以按 `player_id` 稳定展示 story/world/narrative/quest 核心状态
- Intent Debugger 能解释“自然语言 → 世界变化”链路
- Command Observatory 能提供 Equivalent Commands（若可见）
- Narrative Debugger 能展示 current node / candidates / blocked_by
- Scene Explorer 能展示 fragment/theme/tag 结构

---

## 13. 风险与规避

- 风险：接口返回字段在不同分支下不稳定
  - 规避：前端做容错解析，后端补统一响应 schema（后续）

- 风险：Debug 接口依赖 token / 环境变量
  - 规避：UI 提供“无权限提示 + 降级视图”

- 风险：外部资源 API 不稳定
  - 规避：本地缓存索引 + 定时更新，不在用户请求路径强依赖外网

---

## 14. 执行决议

从今天起按此蓝图执行：

1. 先完成 Runtime + Narrative + Scene 的观测与解释闭环；
2. 下一优先级实现 Generation Control（节奏控制）；
3. 然后补 Resource Registry（玩家语义备案）；
4. 最后推进 Graph Editor（IDE 能力）。

> 这是从“引擎已成型、内容待扩张”状态进入产品化最稳健的路线。

---

## 15. Intent Debugger

### Purpose

Explain how natural language input becomes world changes.

### Route

- `/intent/[playerId]`

### Pipeline

```text
Player Input
  ↓
Intent Parse
  ↓
Semantic Match
  ↓
Narrative Decision
  ↓
Scene Selection
  ↓
World Patch
```

### v1 展示模块

- Player Input
- Intent Result（`intent_type / confidence / intent_params`）
- Semantic Match（matched tags / resource mapping / score）
- Narrative Resolution（`current_node / transition_candidates / blocked_by`）
- Scene Selection（selected fragment / theme / semantic tags / pack source）
- World Patch（patch plan + command observability）

---

## 16. Generation Control

### Purpose

Control narrative pacing.

### Route

- `/settings/generation`（已实现）

### Parameters

- `cooldown_seconds`
- `spawn_probability`
- `max_scenes_per_hour`
- `spawn_distance`
- `require_player_movement`
- `require_new_location`

### Policy 执行链路

```text
Event
  ↓
Narrative Decision
  ↓
Scene Generation Policy
  ↓
TRNG
```

### 目标

- 降低连续生成导致的剧情刷屏
- 提供可预测、可调试的场景触发节奏

---

## 17. Command Observatory

### Purpose

Bridge the gap between natural language and Minecraft commands.

### 价值

- 让玩家理解系统行为（Why）
- 让玩家可以手动复现（How）
- 让 Creator 能定位异常链路（Debug）

### Example

Input

`"build a shrine"`

System Output

- Scene: `jungle_temple`
- Patch: `world_patch_294`

Equivalent Commands

- `/setblock`
- `/fill`
- `/summon`

### v1 集成位置

- 集成在 `/intent/[playerId]` 的 World Patch 模块中。
- 命令来源优先级：
  1. backend commands
  2. world_patch translation
  3. fallback mapping
- 原则：优先展示后端返回 commands；若无 commands，则基于 patch 结构做等价命令推导。

---

## 18. System Overview

```text
Minecraft Player
     ↓
   Natural Language
     ↓
  Intent Engine
     ↓
   Narrative Engine
     ↓
 Scene Generation Policy
     ↓
     TRNG
     ↓
    World Patch
     ↓
   Minecraft Runtime

     ↑
   Drift Web Console
```

---

## 19. MC 联调最小闭环（新增）

### 目标

验证以下链路已闭环：

```text
Registry(tag->resource)
  ↓
SpawnFragment
  ↓
Scene Inventory
  ↓
World Patch(meta)
  ↓
Minecraft Plugin
```

### 运行脚本

仓库根目录提供：`./drift_mc_test.sh`

默认测试：

- `tag=shrine`
- `resource=minecraft:lantern`
- 自动多次触发 `spawnfragment`（变更 `scene_hint`）直到通过 policy gate 或达到最大重试

可选参数：

- 位置参数：`./drift_mc_test.sh <BASE_URL> <PLAYER_ID>`
- 环境变量：`TAG`、`RESOURCE_ID`、`MAX_ATTEMPTS`、`TMP_DIR`

### 插件读取建议

`/world/story/{player_id}/spawnfragment` 的 `world_patch` 中透传：

- `world_patch.type = "spawnfragment"`
- `world_patch.meta.registry_resources`
- `world_patch.meta.registry_match_tag`
- `world_patch.meta.registry_bindings_count`

插件侧最小校验建议：优先读取 `world_patch.meta.registry_resources`，作为 `inventory resource -> block placement` 的联调证据。

### 2026-03 线上稳定性补充

- **Registry 覆盖回退**：当 `scene_hint` 未命中任何 tag 时，后端会回退到玩家最近一次 tag 绑定（`match_mode=latest_tag`，`fallback=true`），减少 `registry_resources={}` 概率。
- **最小 Fragment 回退**：当场景选择为空或事件计划为空时，后端会强制注入最小 fragment（默认候选：`fire,camp,shrine`），保证 `event_count > 0` 且生成可执行 `world_patch`。
- **Registry 执行优先级**：当命中 `registry_resources` 时，`spawnfragment` 在 `world_patch` 生成阶段会将 `spawn_block` 相关指令强制替换为 registry 资源（`registry > scene_default`），避免 fragment 默认 `campfire/beacon/platform` 覆盖注册资源。

新增观测字段：

- `world_patch.meta.registry_asset_override`（是否触发执行层覆盖）
- `world_patch.meta.registry_primary_resource`（本次覆盖使用的主资源）

可用环境变量：

- `DRIFT_REGISTRY_FALLBACK_MODE`：`latest_tag`（默认）/`none`
- `DRIFT_SCENE_FALLBACK_FRAGMENTS`：逗号分隔候选（默认 `fire,camp,shrine`）

---

## 20. Drift Phase 1 验收标准（Web → MC 闭环）

### Definition of Done

当前阶段的成功定义：

```text
Web (配置/备案)
  ↓
Backend (registry + policy)
  ↓
MC 玩家自然语言
  ↓
Intent → spawnfragment
  ↓
Scene assembler
  ↓
World patch
  ↓
Minecraft 执行
```

只要上述链路在真实联调中稳定跑通，即可判定本阶段完成。

### 四条硬性验收条件

#### 1) Web 资源备案

玩家可在 Web 注册资源映射（示例）：

- `tag: shrine` → `resource: minecraft:lantern`
- `tag: fire` → `resource: minecraft:campfire`

验收证据（至少一项）：

- `POST /registry/player-tags` 返回成功；
- 后续 `spawnfragment` 响应中出现 `registry_match_tag` 与 `registry_resources`。

#### 2) Web 生成策略可修改

Web 可修改并提交以下策略参数：

- `spawn_probability`
- `spawn_distance`
- `scene_cooldown`

验收证据：

- `POST /settings/generation` 成功；
- 再次读取策略（或后续生成行为）可观察到新值生效。

#### 3) MC 自然语言触发

玩家在 MC 输入自然语言（示例）：

- `生成一个 shrine`
- `build a shrine`

验收证据：

- 后端出现对应触发链路（`intent -> spawnfragment`）；
- `spawnfragment` 返回 `generation_policy_gate.allowed=true` 且 `scene.event_count > 0`（至少一次）。

#### 4) 世界生成对应资源

MC 世界中出现与语义相符的生成结果（示例）：

- `lantern`
- `campfire`
- `platform`
- `beacon`

并在 Web/后端观测到：

- `spawnfragment`
- `generated = true`
- `event_count > 0`

建议同时校验：

- `world_patch.type = spawnfragment`
- `world_patch.meta.registry_resources` 非空（命中注册资源时）

### 最终判定口径

- 四项全部满足：`PASS`
- 任一项不满足：`FAIL`


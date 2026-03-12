# DriftSystem 开发路线图（v0.5 → v0.9）

> 更新时间：2026-03-07
> 目标：在 P1–P5 引擎与运行时工具完成的基础上，推进可玩 AI 叙事沙盒（P6–P9）。

## 1) 当前里程碑（P1–P5 已完成）

### 已完成阶段

- P1：Safe Ground Anchor
- P2：Inventory Canonical Mapping
- P3：NPC Behavior RuleEvents
- P4：Level Evolution Runtime（skeleton）
- P5：World Runtime Tools（Live Runtime Tooling）

### 当前闭环链路

`Minecraft Event → RuleEventBridge → TRNG → Quest Runtime → Level Evolution → Scene Generator → World Patch`

### P5 Runtime Tools（最终集合）

- Debug Tools：`/taskdebug`、`/worldstate`、`/leveldebug`、`/eventdebug`
- Runtime Control：`/spawnfragment`、`/storyreset`

---

## 2) P5 最终验收记录（2026-03-07）

### 服务可用性

- backend `:8000` 监听正常
- Paper `:25565` 监听正常

### 功能验收

- `/world/story/{player}/reset`：`200 ok`，返回 `Story runtime reset completed`
- `/world/story/{player}/spawnfragment`：
  - `fragment_count = 3`
  - `event_count = 3`
  - `world_patch = True`
  - 片段：`camp`、`fire`、`cooking_area`
- `/world/state/{player}`：`ok`
- `/world/story/{player}/debug/tasks`：`ok`

### 结论

P5 正式完成并收口，系统具备完整的 **观察 + 控制 + 复位 + 片段生成** 运行时能力。

---

## 3) 后续蓝图（P6–P9）

### P6-A：Scene Library（先做）

目标：先建立可组合的场景素材库，作为 AI 推理输入与输出空间。

首批建议片段：

- `camp`
- `forge`
- `market`
- `farm`
- `shrine`
- `watchtower`
- `village`

说明：没有 scene library，AI 无法稳定进行场景拼贴与推理。

### P6-B：Resource Semantics（资源语义层）

目标：把原始物品映射到语义标签，支持可解释推理。

当前基线（2026-03-07）：

- 已落地 `semantic_tags.json`（资源 -> 语义标签映射）
- 已落地 `semantic_scoring.json`（fragment 语义权重与打分参数）
- root fragment 由 `priority + semantic_score` 共同决策，保持 deterministic 输出

执行顺序（冻结）：

- P6-B-1：评分明细可解释化（`/eventdebug` 可见 `selected_root/candidate_scores/selected_children/blocked/reasons`）
- P6-B-2：稳定三组 deterministic 分支（camp/forge/village）
- P6-C：诗歌入口原型（仅在 P6-B-1/2 稳定后开启）

P6-B Runtime Verification（2026-03-07）：

- Probe 链路：`/story/inject -> /story/load/{player}/{level} -> /world/story/{player}/debug/tasks`
- Probe 场景：
  - `wood + light + food -> camp`
  - `metal + stone + fire -> forge`
  - `food + trade -> village`
- 运行态结果：
  - roots 三轮稳定：`camp/camp/camp`、`forge/forge/forge`、`village/village/village`
  - `/eventdebug` 同源字段可见：`selected_root` / `candidate_scores` / `selected_children` / `blocked` / `reasons`
  - 分支可分化：三组输入对应三条不同 root
- 证据文件：`logs/runtime_probe/p6b_runtime_probe_1772844803.json`
- 结论：**P6-B 已达到 runtime verified，可封板。**

示例映射：

- `oak_log/spruce_log/birch_log -> wood`
- `torch/lantern -> light`
- `raw_porkchop/beef -> food`

示例推理：

- `wood + light -> camp`
- `food + fire -> cooking_area`
- `stone + iron -> forge`

### P7：Scene Composition（场景拼贴层）

目标：从单片段生成升级为 `scene graph` 组合生成。

示例：

- `camp -> fire -> cooking_area -> watchtower`
- `village -> market -> forge -> farm -> shrine`

输出：稳定、可回放、可执行的 `event_plan/world_patch`。

P7.1 Layout Stabilization（2026-03-07）：

- 范围约束：**先不做 depth-2 graph expansion**，优先稳定 `layout_engine`
- 已实现：`radial_v1 + minimum distance` 防碰撞布局（避免节点重叠）
- 配置项：`DRIFT_LAYOUT_MIN_GAP`（默认 `2`，兼容 `MIN_LAYOUT_GAP`）
- 行为目标：保持 deterministic，同时保证 `scene_graph -> layout -> event_plan(offset)` 可解释
- 回归结果：
  - `python3 -m pytest tests/test_layout_engine.py tests/test_scene_assembler.py tests/test_story_scene_inject_phase7_m2.py -q` -> `34 passed`
  - `python3 tools/p6b_runtime_probe.py --runs 3` -> `overall_pass=True`
- 证据文件：`logs/runtime_probe/p6b_runtime_probe_1772857725.json`

P7.2 Scene Evolution（2026-03-07）：

- 目标：引入 `SceneState + SceneDiff + EvolutionRule`，支持 `rule-event -> 增量扩图 -> 增量 world_patch`。
- 已实现：
  - 新增：`scene_state.py`、`scene_diff.py`、`scene_state_store.py`、`evolution_rules.py`、`scene_evolution.py`。
  - 新增规则：`evolution_rules.json`（v1 范围）
    - `camp: collect:wood -> watchtower`、`collect:stone -> road`
    - `village: collect:food -> farm`、`collect:metal -> forge`
  - `layout_engine.place_new_nodes` 复用最小间距布局，保证增量节点 deterministic 且无重叠。
  - `story/inject` 记录并持久化 `scene_state`，`scene_generation` 包含 `scene_state/scene_diff/incremental_event_plan`。
  - `story/rule-event` 接入演化流程并合并增量 `world_patch`，响应可回传 `scene_diff`。
  - `story/reset` 清理 `scene_state` 持久化，并回传 `cleared_scene_state`。
  - `/eventdebug` 可见 `scene_generation.scene_state` 与 `scene_generation.scene_diff`。
- 回归结果：
  - `python3 -m pytest -q tests/test_layout_engine.py tests/test_scene_assembler.py tests/test_story_scene_inject_phase7_m2.py tests/test_scene_evolution_phase7_p2.py` -> `39 passed`
  - `python3 tools/p6b_runtime_probe.py --runs 3` -> `overall_pass=True`
- 证据文件：`logs/runtime_probe/p6b_runtime_probe_1772860724.json`
- 结论：**P7.2 v1（Scene Evolution）已正式封板，可作为 P8 依赖层。**

### P8：Narrative Engine（叙事引擎）

目标：从任务点推进升级为叙事图推进（Narrative Graph）。

示例路径：

`forest -> camp -> village -> market -> kingdom`

输出：`quest_chain + level_state + narrative_transition` 联动更新。

P8-A Narrative Graph Skeleton（2026-03-07）：

- 本步定位：**只读骨架 + 可观测性**，不做自动推进。
- 已实现：
  - 新增 `narrative_state` 数据结构：`current_arc/current_node/unlocked_nodes/completed_nodes/transition_candidates/blocked_by`。
  - 新增规则文件：`backend/app/content/story/narrative_graph.json`。
  - 新增只读 evaluator：基于 `scene_state + level_state + recent_rule_events` 计算 `transition_candidates`。
  - 接入可观测：`/world/state` 与 `/eventdebug` 均返回
    - `narrative_state`
    - `current_node`
    - `transition_candidates`
    - `blocked_by`
- 约束保证：
  - **不自动推进 story node**
  - **不把 narrative transition 直接耦合到 world_patch**
  - 输出保持 deterministic（同输入同判定）
- 验证结果：
  - `python3 -m pytest -q tests/test_narrative_graph_skeleton_p8a.py` -> `4 passed`
  - `python3 -m pytest -q tests/test_layout_engine.py tests/test_scene_assembler.py tests/test_story_scene_inject_phase7_m2.py tests/test_scene_evolution_phase7_p2.py` -> `39 passed`
  - `python3 tools/p6b_runtime_probe.py --runs 3` -> `overall_pass=True`
- 证据文件：`logs/runtime_probe/p6b_runtime_probe_1772865583.json`

### P9：Asset Layer（资源层，原 Asset Universe）

目标：

将 DriftSystem 从“固定 Scene Library”升级为“可扩展资源层（Asset Layer）”，支持：

- Minecraft Mod 资源
- 结构包（Structure Pack）
- 自定义 fragment pack
- 抽象诗歌 / 文本拼贴
- 世界主题包（World Theme Pack）

最终目标：

`semantic reasoning + scene composition + asset layer = 开放叙事世界生成`

核心思想：

`Semantic AI + Scene Graph + Asset Layer = Open Narrative World`

工程约束（必须）：

- 不破坏 P6–P8 已有 deterministic 与 runtime probe 基线
- 不引入“多套语义表 / 多套 fragment 源”并行维护问题
- 保持 `/eventdebug` 全链路可观测

#### P9-A：Asset Registry（资源注册系统）

目标：

建立统一资源注册表，识别来自不同来源的资产并声明执行方式。

新增模块：

- `asset_registry.json`

结构：

- `asset_id`
- `type`
- `source`
- `semantic_tags`
- `spawn_method`

示例：

```json
{
  "asset_id": "ruined_tower",
  "type": "structure",
  "source": "mod:dungeons_pack",
  "semantic_tags": ["ruin", "stone", "history"],
  "spawn_method": "structure"
}
```

支持来源：

- `vanilla`
- `mod`
- `structure_pack`
- `poetry_fragment`
- `npc_pack`

#### P9-B：Unified Semantic Registry（统一语义注册）

目标：

将 P6-B 与 P9-B 统一为一套语义层，避免 `semantic_tags.json` 与 `mod_semantic_map.json` 双轨漂移。

新增：

- `semantic_registry.json`

示例：

```json
{
  "oak_log": ["wood"],
  "torch": ["light"],
  "rusted_gear": ["metal", "ruin"]
}
```

来源字段：

- `vanilla`
- `mod`
- `pack`

推理流程：

`item/mod asset -> semantic_registry -> semantic scoring -> scene fragment`

#### P9-C：Fragment Registry + Pack System（统一片段注册）

目标：

将 P6-A Scene Library 与 P9-C 外部 pack 统一为单一 fragment registry。

P9-C 实施进度（2026-03-07）：

- P9-C.1 `pack_loader + pack_registry`（metadata scan）✅
- P9-C.2 `asset_registry` 合并 `pack assets`（namespace/priority/conflict）✅
- P9-C.3 `fragment_registry` 合并 `pack fragments` 并接入 `scene_library` ✅
- P9-C.4 `semantic_registry` 合并 `pack semantic_map` 并接入 `semantic_adapter` ✅
- P9-C.5 `theme_registry` 合并 `pack themes` 并接入 `scene_library` ✅

P9-C 封板里程碑：

- `p9c-pack-system`（pack engine 完整版本，支持 semantic/asset/fragment/theme 四层合并）

统一目录：

- `content/fragments/`
  - `vanilla/`
  - `mod/`
  - `pack/`
  - `poetry/`

统一 fragment 结构：

- `fragment_id`
- `source`
- `semantic_requirements`
- `structure_template | generator`
- `children`
- `max_children`

示例：

```yaml
fragment_id: ruined_tower
source: mod:dungeons_pack
semantic_requirements:
  - ruin
  - stone
children:
  - skeleton_camp
  - treasure_room
```

#### P9-D：Poetic Fragment System（诗歌拼贴系统）

目标：

允许抽象文本成为 fragment，并与 scene fragment 组合生成 poetic scene。

新增：

- `poetic_fragments.json`

示例：

```json
{
  "fragment_id": "lonely_fire",
  "text": "一簇火，在无人的林中",
  "semantic_tags": ["fire", "loneliness", "night"],
  "visual_hint": "campfire_small"
}
```

组合路径：

`poetic_fragment + scene_fragment = poetic_scene`

示例：

`lonely_fire + forest = night_camp_scene`

#### P9-E：World Theme Packs（世界主题包）

目标：

让世界具备整体风格并可被主题约束过滤。

新增：

- `world_theme.json`

示例：

```json
{
  "theme": "ruins_world",
  "allowed_fragments": [
    "ruined_tower",
    "abandoned_market",
    "ancient_shrine"
  ]
}
```

推理流程：

`semantic AI -> scene_graph -> theme filter -> world_patch`

#### P9-F：Asset Compiler（资源编译层）

目标：

将异构资产统一编译为系统可执行的 fragment/generator 描述，作为 registry 唯一入口。

输入：

- `schematic`
- `structure block`
- `nbt`
- `mod asset`
- `poetry fragment`

输出：

- `fragment template`（可直接拼贴）
- `generator spec`（可参数化扩展）

编译链路：

`raw assets -> asset compiler -> fragment registry -> scene planner`

#### P9 执行归属（防复杂度爆炸）

采用 `C` 模式（planner + executor）：

- Backend（planner）负责：语义推理、scene graph、layout、event_plan、scene->world_patch 映射
- Plugin（executor）负责：`build_multi/structure/blocks/spawn` 的最终世界执行

约束：

- 生成决策只在 backend
- 世界落地只在 plugin
- 两端仅通过 `world_patch` 契约交互

#### P9 完整生成链路

完成 P9 后：

`Minecraft Event -> RuleEvent -> Resource Semantics -> Scene Graph -> Scene Evolution -> Narrative Graph -> Asset Layer -> Asset Compiler -> World Patch`

系统能力升级为：

`AI Narrative World Engine`

#### P9 验收标准

必须满足：

1) 可扩展

- 新 mod 接入仅需：`asset_registry + semantic_registry (+ compiler rule)`

2) 不破坏 deterministic

- 相同输入（same semantic tags + same theme + same assets + same compiler version）输出一致

3) 可观测

- `/eventdebug` 可看到：`asset_selection`、`fragment_source`、`theme_filter`、`compiler_version`

4) 与 P6–P8 兼容

- 不破坏既有 runtime probe 与回归基线

#### P9 推荐顺序

1. P9-A Asset Registry
2. P9-B Unified Semantic Registry
3. P9-C Fragment Registry + Pack System
4. P9-D Poetic Fragment System
5. P9-E World Theme Packs
6. P9-F Asset Compiler

#### 版本演化（更新）

- P1 Safe Ground
- P2 Inventory Mapping
- P3 NPC RuleEvents
- P4 Level Runtime
- P5 Runtime Tools
- P6 Semantic AI
- P7 Scene Composition
- P7.2 Scene Evolution
- P8 Narrative Engine
- P9 Asset Layer

关键结果：

完成 P9 后 DriftSystem 将升级为 `Narrative AI Sandbox Engine`，并通过统一语义与统一 fragment 注册接入 mod、结构包、poetry 与剧情包。

---

## 4) 推荐开发顺序（执行版）

1. P6-A Scene Library
2. P6-B Resource Semantics
3. P7 Scene Composition
4. P7.2 Scene Evolution
5. P8-A Narrative Graph Skeleton
6. P9-A Asset Registry
7. P8-B Narrative Decision
8. P9-B Unified Semantic Registry
9. P9-C Fragment Registry + Pack System
10. P9-D Poetic Fragment System
11. P9-E World Theme Packs
12. P9-F Asset Compiler

---

## 5) 下一迭代（P9-A）最小交付定义

### 最小目标

- 建立 `asset_registry.json`（含 `asset_id/type/source/semantic_tags/spawn_method`）
- 建立 `semantic_registry.json` 并完成对 P6-B 语义表兼容迁移（避免双轨）
- 建立 `content/fragments/{vanilla,mod,pack,poetry}` 统一目录与 loader
- 保持 scene 选择与 event_plan deterministic，不改变现有 P7/P8 输出契约
- `/eventdebug` 增加 `asset_selection/fragment_source/theme_filter` 字段

### 验收标准

- `deterministic`：同输入稳定得到同 `selected_root/fragment_set/event_plan`
- `observable`：`/eventdebug` 可见 `asset_selection/fragment_source/theme_filter`
- `non-intrusive`：不改变 plugin 执行契约，仅扩展 registry 与 planner 输入
- `regression-safe`：P7.2/P8-A 回归与 runtime probe 持续通过

---

## 6) 紧随迭代（P8-B）最小交付定义

### 最小目标

- 在 `transition_candidates` 基础上引入 `choose_transition`（受控触发，不自动推进）
- 决策输入纳入 P9-A 资产可见性（`asset_registry/theme_filter`），避免“叙事可选但资产不可执行”
- 输出 `narrative_decision`（`chosen_transition/candidate_rank/decision_reason`）并写入审计轨迹
- 保持 `scene_state` / `narrative_state` / `world_patch` 三层解耦，不跨层隐式写入

### 验收标准

- `deterministic`：同输入稳定得到同 `chosen_transition`
- `observable`：`/worldstate` 与 `/eventdebug` 可见 `narrative_decision` 关键字段
- `non-intrusive`：仍为显式触发推进，不引入自动跳转
- `regression-safe`：P7.2/P8-A/P9-A 回归与 runtime probe 持续通过

---

## 7) 回归基线（持续保持）

每轮迭代必须保留以下稳定性验证：

- 事件入口：`collect` / `npc_talk` / `npc_trigger`
- 运行态观测：`/taskdebug` / `/worldstate` / `/eventdebug`
- 控制能力：`/spawnfragment` / `/storyreset`

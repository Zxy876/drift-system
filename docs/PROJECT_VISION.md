# DriftSystem · PROJECT_VISION.md
终极关卡·叙事·场景·规则·任务·主线宇宙愿景  
Version: 1.0  
Status: Living Document（长期保持更新）

---

# 1. OVERVIEW（系统总览）

DriftSystem 是一个 AI × Minecraft 的叙事引擎，让玩家与 AI 在一个不断生长的“心悦宇宙”中共同构建关卡、故事与世界变迁。

系统由五大核心维度构成：

1) **Level（统一格式）**  
2) **Narrative（叙事节拍 beats）**  
3) **Scene（写死场景 + 环境快照）**  
4) **Rules（事件监听 + 行为约束）**  
5) **Tasks（AI 颁布任务 + rule-driven 验收）**  
6) **Exit（自然语言退出剧情 → 回到昆明湖主线）**

这些模块由 StoryEngine、StoryGraph、QuestRuntime、MC 插件桥接与世界补丁系统共同支持。

本文件描述系统的 **终极愿景**（目标宇宙）。  
**STATE.md 始终记录当前世界线（现实状态）。**  
VISION.md 描述未来目标，不代表当前实现。

---

# 2. LEVEL · UNIFIED FORMAT（关卡统一格式愿景）

所有关卡使用统一命名格式：

- 心悦文集关卡：  
  `level_01`, `level_02`, …  

- 玩家创建关卡（时间戳）：  
  `level_20251208_153045`

所有关卡都必须通过统一的叙事管线：### Level 五层结构---

---

# 3. NARRATIVE（叙事与节拍系统愿景）

叙事由 beats（节拍）驱动，提供：

- AI 输出节奏控制  
- 玩家事件触发锚点  
- 场景切换、规则激活、任务变更的触发点  

典型节拍结构：

- beat_intro  
- beat_midpoint  
- beat_conflict  
- beat_climax  
- beat_resolve  

Beats 是 Level 内的叙事时间轴。

StoryGraph 将玩家创建的关卡也纳入叙事网络，实现自动化章节推荐。

---

# 4. SCENE（场景系统愿景）

Scene 是关卡中的“空间层”，用于加载叙事对应的世界快照。

### 1）传送点（Teleport Anchor）### 2）环境层（Environment Layer）
- 天气（weather）  
- 时间（time）  
- 光照（lighting）  
- 粒子/音效/饰品层（可扩展）

### 3）建筑与结构（Structures）
通过结构文件（NBT）加载写死建筑。

### 4）NPC Skin Catalog（写死皮肤）
若关卡需要：
- 美观、特定氛围的 NPC 角色
- 主题角色（如主持人、引导者）

### 场景生命周期控制目标：**完全不污染原世界**（reversible patches）。

---

# 5. RULES（规则系统愿景）

Rules 定义 “监听什么事件 + 触发哪些 AI / task / beat 逻辑”。

监听事件仅限：

- BLOCK_BREAK  
- ENTITY_KILL  
- ITEM_COLLECT  
- DIALOGUE  
- AREA_REACH  
- SUMMON  

且规则只监听 **AI 创建的对象（造物）**，避免全局监听导致过度 AI 请求。

事件 → Rule Listener → QuestRuntimeRules 是任务系统与叙事系统之间的桥。

---

# 6. TASKS（任务系统愿景）

任务包含三部分：

- **conditions**（达成条件）
- **milestones**（阶段性节点）
- **rewards**（奖励）

### 任务来源

1) **新手教学关卡 → 写死任务**  
2) **其他关卡 → AI 根据关卡 scene 和 rules 自动生成任务**

任务类型：

- collect  
- kill  
- reach  
- observe  
- interact  

QuestRuntime 根据 rules 的事件触发进行：任务是关卡体验的动力系统。

---

# 7. EXIT（退出机制愿景）

玩家可以在任意时刻说：

- “结束剧情”
- “退出关卡”
- “我想回主世界”

MC 插件识别 exit → 调用后端：主线任务（昆明湖）以：观察、记录、收集为核心，形成“漂移轨迹”。

---

# 8. STORYGRAPH（剧情图愿景）

StoryGraph 是整个宇宙的叙事结构控制塔：

- 跟踪玩家的关卡进度  
- 决定下一章推荐  
- 将玩家生成的关卡纳入剧情图  
- 根据 beats、任务达成度、剧情分支生成“玩家叙事轨迹”

未来可实现：

- 非线性叙事  
- 多结局  
- 玩家影响剧情网络  

---

# 9. SYSTEM PHASES（系统建设路线图）

系统由 6 个阶段构成：

### Phase 0 — Infrastructure（已完成）
后端、插件、DSL、WorldPatch 基础设施。

### Phase 1 — Unified Level Format（已完成）
level_ 文件格式统一，story_loader 稳定。

### Phase 1.5 — Narrative+Scene+Rules+Tasks+Exit 框架（当前）
目标：
- Level schema 扩展五层结构  
- StoryEngine 加入五大系统入口 hooks  
- Rules/Tasks v1 骨架  
- SceneLoader 桥接准备  
（不要求实际运行所有逻辑）

### Phase 2 — Beat-driven StoryEngine（下一阶段）
- beats → world patches  
- beats → task/state transitions  
- rule-driven beat advancement  

### Phase 3 — Scene Generation & World Synchronization
- 进入剧情 → 加载场景  
- 退出剧情 → 清理场景  

### Phase 4 — AI Task System + NPC Logic
- AI 颁布任务  
- NPC 行为由 rulegraph 驱动  
- 完整任务验收链路  

### Phase 5 — Mainline（昆明湖）· Exit System
- 回到主世界  
- 主线任务：观察、记录、收集漂移  
- 玩家轨迹展示系统  

---

# 10. 设计原则（Design Principles）

1. **世界不能被污染**（reversible world patches）  
2. **AI 输出必须稳定并节拍驱动**  
3. **玩家与 AI 必须拥有共同的可编辑叙事节点（beats）**  
4. **规则只监听 AI 创建的对象，减少噪音与负载**  
5. **所有关卡皆为 Level，玩家关卡不例外**  
6. **STATE.md 是现实；VISION.md 是未来**  

---

# 11. 文件用途声明

- **VISION.md**：长期目标、系统精神、架构方向  
- **STATE.md**：当前世界状态、当前 Phase  
- **LEVEL_FORMAT.md**：实际 JSON 的 schema  
- **blueprints（由 ChatGPT 生成）**：每次开发任务的 patch 清单  

这些文档共同构成 DriftSystem 的世界线与轨迹。

---

# 12. 最终愿景（Summary）

DriftSystem 的终极目标：

**让玩家与 AI 一起创造一个可以“生长”的叙事世界。**

- AI 是导演  
- 玩家是共作者  
- 世界是会因叙事而变化的“可塑型空间”  
- 心悦文集（Heart Universe）是世界的情感内核  
- 昆明湖是主线的原点与归宿  

这就是 DriftSystem 的宇宙。

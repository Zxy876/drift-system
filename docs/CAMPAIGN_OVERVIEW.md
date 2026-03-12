# 心悦旗舰主线概览

## Narrative Arc
- **Tutorial · 心悦之旅序章**：玩家学习基本操作，与心悦向导达成共识，为即将到来的旅程定下「主动发声」的基调。
- **flagship_03 · 风暴之山**：面对高峰与恐惧的具象化，确认「我是会继续往上走的人」的最初承诺。
- **flagship_08 · 心魔迷宫**：雨夜迷宫考验玩家是凝视记忆还是再度退开，决定 emotional flag（`face_once` / `escape_once`）。
- **flagship_12 · 玻璃药店夜行**：在十字路口选择治疗或继续夜行，巩固上一章的倾向并记录循环或面对的行为模式。
- **flagship_final · 黎明回响**：河畔终章根据记忆旗标展开两种结局，晨光之桥或夜行再启，完成第一季主线闭环。

## Emotional Progression
1. **Initiation**：安全的教学氛围中建立「表达=进度」的正向反馈。
2. **Confrontation**：风暴之山通过体感式的雪、风、攀登节奏强化「恐惧被看见」的体验。
3. **Reckoning**：心魔迷宫在雨夜环境中拉长犹豫，利用光线与音乐变化引导真实选择。
4. **Nocturne**：玻璃药店把面对/逃离转换成药店与桥边两条路径，提示玩家：循环也会留下痕迹。
5. **Resolution**：终章根据记忆旗标交付两个情绪节奏——晨光希望或夜行余波，并记录 `xinyue.campaign_complete`。

## Branch Summary
- **Face Path (`xinyue.face_once`)**：
  - 风暴之山晴窗 → 心魔迷宫雨停一隙 → 玻璃药店听见影子 → 终章晨光桥面；
  - 终章触发 `final_face_step/listen`，授予 "晨光回应" 结语与 aurora lighting。
- **Escape Path (`xinyue.escape_once`)**：
  - 风暴之山寒风回声 → 心魔迷宫暗涌加剧 → 玻璃药店夜行循环 → 终章夜潮回环；
  - 终章触发 `final_escape_loop/pause`，保留雨幕音乐并鼓励再次回到主线重来。
- 两条路径都设置 `xinyue.campaign_complete`，方便后续章节或分析区分完成度与情绪倾向。

## Player Agency Philosophy
- **Explicit Guidance, Soft Constraint**：教程 NPC 新增「踏入心悦主线」提示，让玩家知道主线入口，但仍可自由生成/跳关。
- **Memory Flags over Binary Locks**：面对/逃离仅通过情绪场景和对话引导选择，不强制锁死另一条线，保留回溯空间。
- **Cinematic Feedback Loop**：每个关键节点利用音乐、天气、光照反馈玩家选择，强化主观体验而非数值奖励。
- **Replayable Finale**：终章不做绝对结局，而是把当前情绪态度记录在河流中，邀请玩家以不同心态重走主线。

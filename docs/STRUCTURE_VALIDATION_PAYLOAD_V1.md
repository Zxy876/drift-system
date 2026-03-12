# DriftSystem Payload v1 结构可靠性验证

## 1. 验证范围
本次验证仅覆盖 `payload_v1` 的生成与执行链路，包含：
- 生成链路：`compose_scene_and_structure` → `build_plugin_payload_v1`
- 执行链路：`payload_v1.commands(op=setblock)` → 世界状态快照计算（`capture_world_state_snapshot`）

不在本次范围内：`payload_v2` 行为变更验证、TRNG 业务规则正确性验证、线上多玩家并发压测。

---

## 2. 不变量定义（Invariants）

### I-1 Deterministic generation（确定性生成）
- 名称：Deterministic generation
- 精确定义：在相同输入文本、相同固定锚点、相同 `player_id` 下，`payload_v1` 的 `build_id`、`hash.merged_blocks`、完整 payload 的 SHA256 必须一致。
- 必要性：若生成阶段不确定，则同一剧情无法稳定复现，后续执行结果不可审计，不满足结构可靠性。

### I-2 Fixed anchor consistency（固定锚点一致性）
- 名称：Fixed anchor consistency
- 精确定义：在仅改变锚点 `base_x`（例如 `+10`）时，所有命令坐标满足 `x' = x + 10`、`y' = y`、`z' = z`，且 `block` 不变。
- 必要性：锚点是执行空间映射的结构前提；若不保持一致，结构在空间投影中会变形，无法保证可预测执行。

### I-3 Replay consistency（重放一致性）
- 名称：Replay consistency
- 精确定义：同一 `payload_v1` 多次重放（从空世界快照重新应用）得到唯一 `world_state_hash`。
- 必要性：重放一致是“同构输入→同构世界状态”的核心条件；否则系统不可回放、不可验签。

### I-4 Execution integrity（执行完整性）
- 名称：Execution integrity
- 精确定义：每轮执行满足 `executed = expected` 且 `failed = 0`。
- 必要性：结构可靠不仅要求“可生成”，还要求“可完整落地”；若执行缺失或失败，结构可靠性不成立。

### I-5 No side-effect drift（无副作用漂移）
- 名称：No side-effect drift
- 精确定义：对同一 payload 连续应用两次，最终世界哈希与方块数保持不变（幂等）。
- 必要性：若重复执行会产生额外漂移，系统会积累隐式状态污染，不满足长期可维护的结构稳定性。

---

## 3. 验证步骤（可重复步骤）

### I-1 Deterministic generation
#### 验证步骤
1. 输入：剧情文本 `平静夜晚的湖边，建一个7x5木屋`。
2. 固定参数：`origin={base_x:0, base_y:64, base_z:0, anchor_mode:'fixed'}`，`player_id='validator'`。
3. 命令：在仓库根目录执行（示例）
   - `python3 -c "... compose_scene_and_structure + build_plugin_payload_v1 循环3次并输出 build_id/merged_hash/payload_sha256 ..."`
4. 记录每轮 `build_id`、`hash.merged_blocks`、payload SHA256。
5. 期望输出：3 轮三组值完全一致。

### I-2 Fixed anchor consistency
#### 验证步骤
1. 输入同 I-1。
2. 生成两组 payload：
   - A 组锚点：`base_x=0, base_y=64, base_z=0`
   - B 组锚点：`base_x=10, base_y=64, base_z=0`
3. 命令：执行坐标对比脚本（输出 `pairs`、`all_dx10_same_block`、首尾坐标样本）。
4. 逐对比对 `commands(op=setblock)`。
5. 期望输出：`pairs` 全量通过，`all_dx10_same_block=true`。

### I-3 Replay consistency
#### 验证步骤
1. 输入同 I-1。
2. 每轮从空世界快照开始，按 `payload_v1.commands` 生成世界快照哈希。
3. 命令：
   - `python3 -c "... 循环3轮并输出 world_state_hash ..."`
4. 额外复核：读取 `docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/execution_report.json` 中 payload_v1 的 100 轮结果。
5. 期望输出：每个验证集合内 `unique_world_state_hashes=1`。

### I-4 Execution integrity
#### 验证步骤
1. 输入同 I-1。
2. 每轮统计：
   - `expected = len(commands)`
   - `executed = count(op=setblock)`
   - `failed = expected - executed`
3. 命令：
   - `python3 -c "... 输出 expected/executed/failed（3轮）..."`
4. 期望输出：每轮 `executed=expected`，每轮 `failed=0`。

### I-5 No side-effect drift
#### 验证步骤
1. 输入同 I-1。
2. 用同一 payload 生成两次世界快照：
   - 第一次：`snapshot(commands)`
   - 第二次：`snapshot(commands + commands)`
3. 命令：
   - `python3 -c "... 输出 no_drift_once_hash/no_drift_twice_hash 与方块计数 ..."`
4. 对比两次哈希与方块计数。
5. 期望输出：哈希相等且方块计数相等。

---

## 4. 可量化结果

### I-1 Deterministic generation
- 统计次数：3 轮。
- `scene_block_count=198`，`merged_block_count=293`。
- 3 轮一致值：
  - `build_id=06c0c2ff411bf657e29a0a020e84ba343aaa4a093625b6255bd8280652abbdfa`
  - `hash.merged_blocks=489e47b2521a84cfcea66ce2e83cf9c1690c82f44e017bbf41ab642a5b822cd2`
  - `payload_sha256=9ff2187a6dba929d65cbcf87b0240ab47e745e86e4517b17ed8dc229552a67da`
- 结果：3/3 完全一致。

### I-2 Fixed anchor consistency
- 统计次数：293 对坐标（全量 setblock 命令对）。
- 对比结果：`all_dx10_same_block=true`。
- 坐标样本：
  - 首命令：`(-1,64,-1)` → `(9,64,-1)`
  - 末命令：`(12,64,12)` → `(22,64,12)`
- block 一致性：293/293 保持相同 block id。

### I-3 Replay consistency
- 本地 3 轮重放：
  - `world_state_hash` 全部为 `97993f91649ce06ca8d5a84340619670dbf31426ba01a9c76d5d39f1efe68959`
  - `unique_world_state_hashes=1`
- 历史 100 轮复核（payload_v1）：`docs/payload_v2/evidence/gate2/snapshot_rule_v2_2/execution_report.json`
  - `fog-only`：`unique_world_state_hashes=1`，`world_state_hash_counts[8a846e...]=100`
  - `npc-only`：`unique_world_state_hashes=1`，`world_state_hash_counts[763d04...]=100`
  - `fog+npc`：`unique_world_state_hashes=1`，`world_state_hash_counts[80ed73...]=100`
- 结果：本地与历史批次均满足唯一哈希。

### I-4 Execution integrity
- 统计次数：3 轮。
- 每轮数值：
  - `expected=293`
  - `executed=293`
  - `failed=0`
- 汇总：
  - `executed/expected = 879/879`
  - `failed_total=0`
- 结果：`executed=expected` 且 `failed=0` 在 3 轮全部成立。

### I-5 No side-effect drift
- 统计次数：同一 payload 连续应用 2 次（一次 vs 二次）。
- 哈希对比：
  - `no_drift_once_hash=97993f91649ce06ca8d5a84340619670dbf31426ba01a9c76d5d39f1efe68959`
  - `no_drift_twice_hash=97993f91649ce06ca8d5a84340619670dbf31426ba01a9c76d5d39f1efe68959`
- 方块计数对比：
  - `no_drift_once_count=293`
  - `no_drift_twice_count=293`
- 结果：哈希与计数均一致，无额外副作用漂移。

---

## 5. 结果截图占位

### I-1 Deterministic generation
[截图占位：3 轮 build_id / merged_hash / payload_sha256 对比输出]

### I-2 Fixed anchor consistency
[截图占位：base_x=0 与 base_x=10 的首尾坐标及 all_dx10_same_block=true 输出]

### I-3 Replay consistency
[截图占位：本地 3 轮 world_state_hash 一致输出 + gate2 历史 100 轮报告片段]

### I-4 Execution integrity
[截图占位：3 轮 expected/executed/failed 统计输出（293/293/0）]

### I-5 No side-effect drift
[截图占位：一次执行与二次执行的 world_state_hash 和 world_block_count 对比输出]

---

## 6. 结论
基于第 4 节量化结果，`payload_v1` 当前满足以下结构可靠性条件：
- 满足确定性生成：同输入 3 轮 `build_id/hash/payload_sha256` 全一致。
- 满足固定锚点一致性：293/293 命令对满足 `dx=10, dy=0, dz=0` 且 block 不变。
- 满足重放一致性：本地 3 轮与历史 100 轮均为唯一世界哈希。
- 满足执行完整性：累计 `executed/expected=879/879`，`failed_total=0`。
- 满足无副作用漂移：一次/二次应用哈希与方块计数一致（293）。

仍存在风险（基于当前验证边界）：
- 本次执行验证为 `payload_v1` 命令级世界快照重放；未覆盖真实线上插件在高并发、跨版本服务端、异常网络条件下的回传抖动。
- 验证输入集当前以“7x5 木屋”与 gate2 场景集为主，尚未形成大规模语义覆盖矩阵。

是否可支撑下一阶段（TRNG 改造）：
- 结论：可以支撑。
- 依据：5 条结构不变量均被量化数据满足，且未出现 `failed>0`、哈希分叉、锚点漂移或二次执行污染。
- 前置约束：TRNG 进入联调后需补充“并发回传一致性”和“异常恢复重放一致性”两类增量验证。
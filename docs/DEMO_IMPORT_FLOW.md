# Demo 导入流程（HTTP A 路线）

目标：把“长文本关卡导入”从游戏聊天解耦，通过 HTTP 导入，再到游戏里触发执行，验证 `plugin_payload_v1` 与回传闭环。

## 1) 启动前环境变量

后端启动前设置：

```bash
export DRIFT_USE_PAYLOAD_V1=true
export DRIFT_FIXED_ANCHOR_X=0
export DRIFT_FIXED_ANCHOR_Y=64
export DRIFT_FIXED_ANCHOR_Z=0
```

## 2) 准备文本

```bash
cat > /tmp/level.txt <<'TXT'
平静夜晚的湖边，有一座 7x5 的木屋，门朝南，开两扇窗。
TXT
```

## 3) HTTP 导入

```bash
PLAYER=vivn BASE=http://127.0.0.1:8000 ./scripts/inject_story.sh /tmp/level.txt
```

预期：
- 当 `DRIFT_USE_PAYLOAD_V1=true` 时，返回 JSON 包含 `version=plugin_payload_v1`、`build_id`、`commands`、`hash`。
- 当开关关闭时，返回 legacy 注入结构（兼容模式）。

## 4) 进游戏触发应用

1. 先传送到 anchor：

```mcfunction
/tp <你的ID> 0 64 0
```

2. 在聊天触发 `CREATE_STORY`（例如：`创建剧情` / `导入剧情` / `开始关卡`）。

3. 观察聊天提示（插件侧）：
- `开始生成场景... build_id=...`
- `[DEBUG] build_id=... origin=(x,y,z) first_block=(x,y,z)`

如果看不到方块，先 `/tp` 到 `first_block` 附近再观察。

## 5) 验证执行回传

```bash
curl -sS "http://127.0.0.1:8000/world/story/vivn/debug/tasks" | python3 -m json.tool
```

关注字段：
- `last_apply_report.last_status`：`EXECUTED` / `PARTIAL` / `REJECTED`
- `last_apply_report.last_executed`：应大于 0（表示确实执行了落块）
- `last_apply_report.last_failure_code`：拒绝/失败原因
- `recent_apply_reports`：同 `build_id` 幂等去重

## 6) 常见判定

- `EXECUTED` 但肉眼无变化：大概率是站位不在 `origin/first_block` 附近。
- `REJECTED`：看 `last_failure_code`（如 `QUEUE_FULL` / `INVALID_BLOCK_ID` / `TOO_MANY_BLOCKS`）。
- 没有 `last_apply_report`：通常是未命中 payload 链路（开关未生效或未触发对应意图）。

## 7) 观测与口播模板

推荐使用观测脚本（更适合现场 demo 口播）：

```bash
PLAYER=vivn BASE=http://127.0.0.1:8000 ./scripts/check_apply_report.sh
```

可选：

```bash
# 输出 last_apply_report 原始 JSON
PLAYER=vivn BASE=http://127.0.0.1:8000 ./scripts/check_apply_report.sh --json

# 输出最近 3 条 build 的状态摘要
PLAYER=vivn BASE=http://127.0.0.1:8000 ./scripts/check_apply_report.sh --recent 3
```

口播示例：

> 这次构建 `build_id=...`，状态是 `last_status=EXECUTED`，
> 实际执行了 `last_executed=293` 个方块，失败 `last_failed=0`，
> 耗时 `last_duration_ms=420ms`，回传哈希 `last_payload_hash=...`。

若脚本提示 `last_apply_report not found`（退出码 2），说明当前玩家还没有执行回传；优先检查是否命中 `CREATE_STORY` 与 payload 链路。

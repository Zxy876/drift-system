

ONLINE_BACKEND_REASON_VERIFICATION

1. 验证目标

本验证通过纯后端接口证明以下四点：
	1.	payload_v1 分支已在线上生效。
	2.	生成逻辑在相同输入下为 deterministic（结构哈希一致）。
	3.	未触发 fallback 分支。
	4.	系统具备可观测的 debug 状态输出。

本验证不依赖游戏客户端，仅通过 HTTP 接口完成。

⸻

2. 前置条件
	•	Railway 已部署 main。
	•	环境变量：
	•	DRIFT_USE_PAYLOAD_V1=true
	•	DRIFT_USE_PAYLOAD_V2=false
	•	线上地址：

https://driftsystem-production-6558.up.railway.app

	•	OpenAPI 文档：
  https://driftsystem-production-6558.up.railway.app/docs

/docs
/openapi.json


⸻

3. 验证原理说明

3.1 Deterministic 定义

在以下字段完全相同的前提下：
	•	title
	•	text
	•	player_id

仅改变 level_id（用于避免资源唯一性冲突）

若三次请求返回的：

hash.merged_blocks

完全一致，则生成函数为 deterministic。

说明：
	•	level_id 仅为资源存储标识
	•	生成结构只依赖语义输入

⸻

4. 接口说明

4.1 POST /story/inject

关键返回字段：
	•	version
	•	build_id
	•	hash.merged_blocks
	•	commands

验证重点：
	•	version == plugin_payload_v1
	•	commands.length > 0

⸻

4.2 GET /world/story/{player_id}/debug/tasks

关键字段：
	•	last_fallback_flag
	•	last_fallback_reason
	•	recent_apply_reports

⸻

5. 可重复验证步骤

⸻

Step 1：Deterministic 验证（方法 A）

1. 设置固定输入

BASE="https://driftsystem-production-6558.up.railway.app"
PLAYER="railway_validator"
TITLE="railway payload_v1 verify"
TEXT="平静夜晚的湖边，有一座7x5木屋，门朝南，开两扇窗"


⸻

2. 三次 inject（不同 level_id）

curl -sS -X POST "$BASE/story/inject" \
  -H "Content-Type: application/json" \
  -d '{"level_id":"railway_payload_v1_verify_A1","title":"'"$TITLE"'","text":"'"$TEXT"'","player_id":"'"$PLAYER"'"}' > /tmp/inject_1.json

curl -sS -X POST "$BASE/story/inject" \
  -H "Content-Type: application/json" \
  -d '{"level_id":"railway_payload_v1_verify_A2","title":"'"$TITLE"'","text":"'"$TEXT"'","player_id":"'"$PLAYER"'"}' > /tmp/inject_2.json

curl -sS -X POST "$BASE/story/inject" \
  -H "Content-Type: application/json" \
  -d '{"level_id":"railway_payload_v1_verify_A3","title":"'"$TITLE"'","text":"'"$TEXT"'","player_id":"'"$PLAYER"'"}' > /tmp/inject_3.json


⸻

3. 抽取关键字段

for i in 1 2 3; do
  echo -n "run=$i "
  jq -r '"version="+.version+" merged_hash="+.hash.merged_blocks+" commands="+(.commands|length|tostring)' /tmp/inject_${i}.json
done


⸻

4. 校验 hash 一致性

for i in 1 2 3; do
  jq -r '.hash.merged_blocks' /tmp/inject_${i}.json
done | sort | uniq -c


⸻

Step 1 期望值
	•	3/3 version == plugin_payload_v1
	•	3/3 commands.length > 0
	•	3/3 hash.merged_blocks 完全一致
	•	不返回 world_preview 字段

⸻

Step 2：Fallback 验证

curl -sS "$BASE/world/story/$PLAYER/debug/tasks" > /tmp/debug.json

抽取：

jq '{last_fallback_flag,last_fallback_reason,recent_apply_reports}' /tmp/debug.json


⸻

Step 2 期望值
	•	last_fallback_flag == false
	•	last_fallback_reason == "none"
	•	recent_apply_reports 字段存在

⸻

6. 量化验收标准

验证通过必须满足：
	•	hash.merged_blocks：3/3 一致
	•	commands.length：3/3 > 0
	•	version：3/3 == plugin_payload_v1
	•	last_fallback_flag=false
	•	返回 JSON 不包含 world_preview

⸻

7. 失败判定条件

任一条件触发即判定失败：
	•	version != plugin_payload_v1
	•	hash.merged_blocks == null
	•	3 次 hash 不一致
	•	commands.length == 0
	•	出现 world_preview
	•	last_fallback_flag == true
	•	HTTP != 200

⸻

8. 结论逻辑链

若以上全部成立，则：
	1.	生成逻辑 deterministic
	2.	payload_v1 分支生效
	3.	fallback 未触发
	4.	结构可观测

即：线上结构可靠。

 
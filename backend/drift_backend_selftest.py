import requests
import json
from pprint import pprint

BASE = "http://127.0.0.1:8000"
PLAYER = "test_player"
TEST_LEVEL_ID = "level_1"
TIMEOUT = 15


def pretty(title, data):
    print("\n" + "=" * 60)
    print(">>> " + title)
    print("-" * 60)
    if isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))


# -------------------------------------------------------------
# 1. /story/levels
# -------------------------------------------------------------
def test_story_levels():
    print("\n[1] 测试 /story/levels")
    r = requests.get(f"{BASE}/story/levels", timeout=TIMEOUT)
    pretty("关卡列表", r.json())
    return r.json()


# -------------------------------------------------------------
# 2. /story/load/{player}/{level_id}
# -------------------------------------------------------------
def test_story_load():
    print("\n[2] 测试 /story/load/{player}/{level_id}")
    url = f"{BASE}/story/load/{PLAYER}/{TEST_LEVEL_ID}"
    r = requests.post(url, json={}, timeout=TIMEOUT)
    pretty("加载关卡返回", r.json())
    return r.json()


# -------------------------------------------------------------
# 3. /story/advance/{player}
# -------------------------------------------------------------
def test_story_advance_say(content: str):
    print(f"\n[3] 测试 /story/advance/{PLAYER}  自然语言: {content!r}")

    payload = {
        "say": content,             # ← 你后端真实字段
        "world_state": {},          # optional
        "tree_state": {}            # optional
    }

    url = f"{BASE}/story/advance/{PLAYER}"
    r = requests.post(url, json=payload, timeout=TIMEOUT)
    pretty("推进剧情返回", r.json())
    return r.json()


# -------------------------------------------------------------
# 4. tree 系统
# -------------------------------------------------------------
def test_tree_add_and_state():
    print("\n[4] 测试 Tree 系统")

    # POST /tree/add
    payload = {"content": "我拒绝这个安排，我要走向湖对面的塔楼。"}
    r = requests.post(f"{BASE}/tree/add", json=payload, timeout=TIMEOUT)
    pretty("Tree /add 返回", r.json())

    # GET /tree/state
    r2 = requests.get(f"{BASE}/tree/state", timeout=TIMEOUT)
    pretty("Tree /state 返回", r2.json())

    # POST /tree/backtrack
    r3 = requests.post(f"{BASE}/tree/backtrack", json={}, timeout=TIMEOUT)
    pretty("Tree /backtrack 返回", r3.json())


# -------------------------------------------------------------
# 5. DSL 注入剧情
# -------------------------------------------------------------
def test_dsl_run_and_levels():
    print("\n[5] 测试 /dsl/run 注入剧情")

    script = """
    {
      "level_id": "dsl_test",
      "title": "来自 DSL 的测试关卡",
      "summary": "这是从 DSL 注入的剧情",
      "entry_node": {
        "title": "DSL 入口",
        "text": "你进入了脚本生成的世界。"
      }
    }
    """

    r = requests.post(f"{BASE}/dsl/run", json={"script": script}, timeout=TIMEOUT)
    pretty("DSL /run 返回", r.json())

    # 再查 levels
    r2 = requests.get(f"{BASE}/story/levels", timeout=TIMEOUT)
    pretty("DSL 注入后 /story/levels 返回", r2.json())

    has_dsl = any(
        x.get("id") == "dsl_test"
        for x in r2.json().get("levels", [])
    )
    print("\n[检查] 关卡列表是否包含 dsl_test:", has_dsl)
    return has_dsl


# -------------------------------------------------------------
if __name__ == "__main__":
    print("=== DriftSystem 后端能力自检 ===")

    test_story_levels()
    test_story_load()

    test_story_advance_say("我环顾四周。")
    test_story_advance_say("在我旁边生成一张桌子和一把椅子。")
    test_story_advance_say("召唤一个叫小玉兔的兔子 NPC 和我说话。")

    test_tree_add_and_state()
    test_dsl_run_and_levels()

    print("\n=== 后端测试完成 ===")
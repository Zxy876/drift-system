import os
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class HintEngine:
    def __init__(self, tree_engine):
        self.tree_engine = tree_engine
        
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        model = os.getenv("OPENAI_MODEL")

        if not api_key:
            raise ValueError("❌ OPENAI_API_KEY 未设置")
        if not base_url:
            raise ValueError("❌ OPENAI_BASE_URL 未设置")

        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    # ---------------------------------------------------------
    # 清理 AI JSON 字符串
    # ---------------------------------------------------------
    def clean_json_string(self, s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s.strip("`")
            s = s.replace("json", "")
            s = s.strip()
        return s

    # ---------------------------------------------------------
    # get_hint 核心逻辑
    # ---------------------------------------------------------
    def get_hint(self, content: str):
        state = self.tree_engine.export_state()
        current = state["current"]

        # Prompt
        prompt = f"""
你是一个严格的 JSON 输出机器。必须遵守以下规则：

⚠️ 绝对禁止：
- 自然语言解释
- markdown
- ```json 或任何反引号
- 非 JSON 内容
- action.value 是字符串
- 空字符串作为返回值

⚠️ 你只能返回严格 JSON。格式 EXACT：

{{
  "summary": "一句话总结",
  "reasoning": "一句话推理方向",
  "action": null 或 {{
      "type": "set" 或 "add",
      "key": "speed" 或 "angle" 或 "friction",
      "value": 数字（不能是字符串）
  }}
}}

如果用户表达不明确，必须返回：
"action": null

用户输入：{content}
当前节点：{current}
"""

        # 调用模型
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            msg = resp.choices[0].message.content.strip()
        except Exception as e:
            return {"error": f"AI 调用失败：{e}"}

        # 清理 JSON
        msg = self.clean_json_string(msg)

        # 解析 JSON
        try:
            result = json.loads(msg)
        except Exception:
            return {"error": "AI 返回了非法 JSON", "raw": msg}

        # ---------------------------------------------------------
        # 自动修复 action.value（字符串 → 数字）
        # ---------------------------------------------------------
        action = result.get("action")
        if isinstance(action, dict):
            val = action.get("value")

            if isinstance(val, str):
                # 模糊语言 → 自动映射
                if any(k in val for k in ["一点", "少许", "稍微"]):
                    action["value"] = 1
                elif any(k in val for k in ["更", "多"]):
                    action["value"] = 2
                else:
                    action["value"] = 1  # fallback
            
            if action.get("value") is None:
                result["action"] = None

        # ---------------------------------------------------------
        # 执行 world/apply
        # ---------------------------------------------------------
        if result.get("action"):
            try:
                world_resp = requests.post(
                    "http://127.0.0.1:8000/world/apply",
                    json={"action": result["action"]}
                )
                try:
                    result["world_apply"] = world_resp.json()
                except Exception:
                    result["world_apply"] = {"raw": world_resp.text}
            except Exception as e:
                result["world_apply"] = {"error": str(e)}

        return {
            "input": content,
            "current_node": current,
            "result": result
        }
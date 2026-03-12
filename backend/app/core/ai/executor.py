def build_action(intent: str, parsed: dict, player_id: str, message: str):

    if intent == "chat":
        return {
            "reply": f"§d[心悦AI]§r {message}",
            "command": "none"
        }

    if intent == "load_level":
        if parsed.get("level"):
            return {
                "reply": f"准备进入心悦文集第 {parsed['level']} 关",
                "command": "story_load",
                "args": {"player": player_id, "level": parsed["level"]}
            }
        return {
            "reply": "你想进入第几关？",
            "command": "ask_level"
        }

    if intent == "story":
        return {
            "reply": "故事继续前行…",
            "command": "story_advance",
            "args": {"player": player_id}
        }

    if intent == "dsl":
        return {
            "reply": "执行 DSL…",
            "command": "dsl",
            "args": {"script": parsed["raw"]}
        }

    if intent == "world":
        return {
            "reply": "世界正在变动…",
            "command": "world_patch",
            "args": {"text": parsed["raw"]}
        }

    if intent == "npc":
        return {
            "reply": "她向你走来…",
            "command": "npc",
            "args": {"text": parsed["raw"]}
        }

    if intent == "event":
        return {
            "reply": "昆明湖宇宙正在苏醒…",
            "command": "universe_event",
            "args": {"event": parsed["raw"]}
        }

    return {
        "reply": "我听到了，但不太确定你的意思。",
        "command": "none"
    }

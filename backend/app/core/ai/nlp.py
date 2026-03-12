import re

INTENT = {
    "story":      ["继续", "推进", "下一步", "然后呢", "advance", "故事"],
    "load_level": ["进入第", "进入关卡", "加载关卡", "玩第", "level", "第", "关"],
    "dsl":        ["画", "生成", "构建", "创造", "dsl", "脚本", "放光", "特效"],
    "world":      ["天空", "地面", "爆炸", "裂开", "变色", "天气"],
    "npc":        ["跟着我", "跟随", "npc", "说", "和我说"],
    "event":      ["宇宙", "昆明湖", "异象", "事件", "裂缝"],
}

def classify_intent(text: str):
    text = text.lower()

    m = re.search(r"第\s*(\d+)\s*关", text)
    level_num = int(m.group(1)) if m else None

    for intent, words in INTENT.items():
        for w in words:
            if w in text:
                return intent, {
                    "level": level_num,
                    "raw": text
                }

    return "chat", {"raw": text}

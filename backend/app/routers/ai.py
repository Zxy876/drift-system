from fastapi import APIRouter

router = APIRouter()

@router.post("/suggest")
def suggest(text: str):
    # v0.1：假 AI（你可以之后接 OpenAI）
    return {
        "suggestion": "我觉得你可以尝试把问题拆成更具体的两个子问题。",
        "note": "此处为占位示例"
    }

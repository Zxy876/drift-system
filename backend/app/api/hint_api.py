from fastapi import APIRouter
from pydantic import BaseModel
from app.core.hint.engine import HintEngine
from app.core.tree.engine import TreeEngine

router = APIRouter()
tree_engine = TreeEngine()
engine = HintEngine(tree_engine)

class HintInput(BaseModel):
    content: str

@router.post("/")
def hint(data: HintInput):
    return engine.get_hint(data.content)

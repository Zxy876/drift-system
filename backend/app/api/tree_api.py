from fastapi import APIRouter
from pydantic import BaseModel
from app.core.tree.engine import TreeEngine

router = APIRouter()
engine = TreeEngine()

class AddNodeInput(BaseModel):
    content: str

@router.post("/add")
def add_node(data: AddNodeInput):
    return engine.add(data.content)

@router.get("/state")
def get_state():
    return engine.export_state()

@router.post("/backtrack")
def backtrack():
    return engine.backtrack()

@router.post("/breakpoint")
def set_breakpoint():
    return engine.breakpoint()

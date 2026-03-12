from fastapi import APIRouter
from app.core.drift_tree import DriftTree

router = APIRouter()

session_tree = DriftTree()

@router.post("/start")
def start_problem(text: str):
    root = session_tree.add_root(text)
    return {"root": root, "tree": session_tree.to_dict()}

@router.post("/add")
def add_node(parent_id: str, text: str):
    cid = session_tree.add_child(parent_id, text)
    return {"child": cid, "tree": session_tree.to_dict()}

@router.get("/tree")
def get_tree():
    return session_tree.to_dict()

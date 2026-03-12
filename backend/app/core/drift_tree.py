from typing import List, Optional
from pydantic import BaseModel
import uuid

class DriftNode(BaseModel):
    id: str
    text: str
    parent: Optional[str] = None
    children: List[str] = []
    state: str = "active"

class DriftTree(BaseModel):
    nodes: dict = {}

    def add_root(self, text: str):
        root_id = str(uuid.uuid4())
        self.nodes[root_id] = DriftNode(id=root_id, text=text)
        return root_id

    def add_child(self, parent_id: str, text: str):
        cid = str(uuid.uuid4())
        self.nodes[cid] = DriftNode(id=cid, text=text, parent=parent_id)
        self.nodes[parent_id].children.append(cid)
        return cid

    def to_dict(self):
        return {nid: node.dict() for nid, node in self.nodes.items()}

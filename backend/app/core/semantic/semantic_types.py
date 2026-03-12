from typing import List, TypedDict


class SemanticResult(TypedDict):
    item_id: str
    semantic_tags: List[str]
    source: str
    adapter_hit: bool

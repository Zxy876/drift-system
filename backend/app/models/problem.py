from pydantic import BaseModel
from typing import Optional

class Problem(BaseModel):
    id: str
    title: str
    body: str
    difficulty: str
    answer: Optional[str] = None

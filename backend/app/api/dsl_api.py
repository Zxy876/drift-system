from fastapi import APIRouter
from pydantic import BaseModel
from app.core.dsl.parser import parse_dsl

router = APIRouter()

class DSLInput(BaseModel):
    script: str

@router.post("/run")
async def run_dsl(data: DSLInput):
    ast = parse_dsl(data.script)
    return {
        "dsl": data.script,
        "ast": ast,
        "status": "ok"
    }
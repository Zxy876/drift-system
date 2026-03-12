from fastapi import APIRouter
from app.core.problem_bank import get_random, load_all

router = APIRouter()

@router.get("/random")
def random_problem():
    return get_random()

@router.get("/all")
def all_problems():
    return load_all()

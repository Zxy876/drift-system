import json, os
from app.models.problem import Problem
from typing import List
import random

DATA_DIR = "data/problems"

def load_all() -> List[Problem]:
    problems = []
    for file in os.listdir(DATA_DIR):
        if file.endswith(".json"):
            with open(f"{DATA_DIR}/{file}", "r") as f:
                problems.append(Problem(**json.load(f)))
    return problems

def get_random() -> Problem:
    all_p = load_all()
    return random.choice(all_p)

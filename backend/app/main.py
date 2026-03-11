# backend/app/main.py

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Routers
from app.api.tree_api import router as tree_router
from app.api.dsl_api import router as dsl_router
from app.api.hint_api import router as hint_router
from app.api.world_api import router as world_router
from app.api.story_api import router as story_router
from app.api.npc_api import router as npc_router
from app.api.tutorial_api import router as tutorial_router
from app.api.registry_api import router as registry_router
from app.api.intent_api import router as intent_router
from app.api.scenes_api import router as scenes_router
from app.api.narrative_api import router as narrative_router
from app.api.settings_api import router as settings_router
from app.api.poetry_api import router as poetry_router
from app.routers import ai_router
from app.routers.minimap import router as minimap_router
from app.api.minimap_api import router as minimap_png_router

# Core
from app.core.story.story_loader import list_levels, load_level
from app.core.story.story_engine import story_engine


# -----------------------------
# App 初始化
# -----------------------------
app = FastAPI(title="DriftSystem · Heart Levels + Story Engine")


SERVICE_NAME = "drift-backend"
SERVICE_VERSION = str(os.environ.get("DRIFT_BACKEND_VERSION") or "0.1").strip() or "0.1"


# -----------------------------
# CORS（允许前端/MC 调用）
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# 注册全部路由
# -----------------------------
app.include_router(tree_router,        tags=["Tree"])
app.include_router(dsl_router,         tags=["DSL"])
app.include_router(hint_router,        tags=["Hint"])
app.include_router(world_router,       tags=["World"])
app.include_router(story_router,       tags=["Story"])
app.include_router(npc_router,         tags=["NPC"])
app.include_router(tutorial_router,    tags=["Tutorial"])
app.include_router(registry_router,    tags=["Registry"])
app.include_router(intent_router,      tags=["Intent"])
app.include_router(scenes_router,      tags=["Scenes"])
app.include_router(narrative_router,   tags=["Narrative"])
app.include_router(settings_router,    tags=["Settings"])
app.include_router(poetry_router,      tags=["Poetry"])
app.include_router(ai_router.router,   tags=["AI"])
app.include_router(minimap_router,     tags=["MiniMap"])
app.include_router(minimap_png_router, tags=["MiniMapPNG"])


# -----------------------------
# 启动日志（不再访问不存在的属性）
# -----------------------------
print(">>> DriftSystem loaded: TREE + DSL + HINT + WORLD + STORY + REGISTRY + SCENES + NARRATIVE + SETTINGS + POETRY + AI + MINIMAP + PNG")
print(">>> Total Levels:", len(story_engine.graph.all_levels()))
print(">>> Spiral triggers:", len(story_engine.minimap.positions))
print(">>> Heart Universe backend ready.")


# -----------------------------
# Levels API
# -----------------------------
@app.get("/levels")
def api_list_levels():
    return {"status": "ok", "levels": list_levels()}


@app.get("/levels/{level_id}")
def api_get_level(level_id: str):
    try:
        lv = load_level(level_id)
        return {"status": "ok", "level": lv.__dict__}
    except FileNotFoundError:
        return {"status": "error", "msg": f"Level {level_id} not found"}


# -----------------------------
# Home / 状态
# -----------------------------
@app.get("/")
def home():
    return {
        "status": "running",
        "routes": [
            "/levels",
            "/story/*",
            "/world/*",
            "/registry/*",
            "/scenes/*",
            "/narrative/*",
            "/settings/*",
            "/poetry/*",
            "/ai/*",
            "/minimap/*",
            "/minimap/png/*",
        ],
        "story_state": story_engine.get_public_state(),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }
# backend/app/api/minimap_api.py
from fastapi import APIRouter, Response
import base64
from pathlib import Path

from app.core.story.story_engine import story_engine
from app.core.world.minimap_renderer import MiniMapRenderer  # 你缺这个文件

router = APIRouter(prefix="/minimap", tags=["MiniMap"])
renderer = MiniMapRenderer()

@router.get("/png/{player_id}")
def get_png(player_id: str):
    data = story_engine.minimap.to_dict(player_id)
    nodes = data["nodes"]
    pos = data.get("player_pos")
    current = data.get("current_level")

    png_path = renderer.render(nodes, pos, current)

    with open(png_path, "rb") as f:
        return Response(f.read(), media_type="image/png")


@router.get("/give/{player_id}")
def give_map(player_id: str):
    data = story_engine.minimap.to_dict(player_id)
    png_path = renderer.render(data["nodes"], data.get("player_pos"), data.get("current_level"))

    with open(png_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    return {
        "status": "ok",
        "mc": {
            "tell": "🗺 小地图已生成。",
            "give_item": "filled_map",
            "map_image": b64
        }
    }
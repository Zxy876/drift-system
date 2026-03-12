from fastapi import APIRouter
from pydantic import BaseModel
import subprocess

router = APIRouter()

# --------------------------------------------------------
# 接口数据模型
# --------------------------------------------------------
class BuildStageRequest(BaseModel):
    stage_id: int


# --------------------------------------------------------
#  生成场景（Minecraft 执行 setblock / fill）
# --------------------------------------------------------
@router.post("/build")
def build_stage(req: BuildStageRequest):
    stage = req.stage_id

    if stage == 1:
        # 昆明湖 · 浅湖梦境
        cmds = [
            # 清空 12×12 区域
            "fill ~-6 ~ ~-6 ~6 ~ ~6 air",

            # 填湖底
            "fill ~-6 ~-1 ~-6 ~6 ~-1 ~6 dirt",

            # 加水（浅湖）
            "fill ~-6 ~ ~-6 ~6 ~ ~6 water",

            # 左侧掉落石块
            "setblock ~-5 ~1 ~-3 stone",
            "setblock ~-4 ~2 ~-2 stone",
            "setblock ~-5 ~3 ~1 stone",
            "setblock ~-3 ~1 ~2 stone",

            # 右侧“教书先生”的讲台
            "setblock ~4 ~ ~0 lectern",
            "setblock ~4 ~ ~1 oak_planks",

            # 舒缓雾气（视觉效果）
            "effect give @p minecraft:blindness 1 0 true"
        ]

        # exec
        for c in cmds:
            subprocess.run(["rcon-cli", c])

        return {"status": "ok", "stage": "昆明湖 · 填湖梦境"}
    
    return {"status": "unknown stage"}

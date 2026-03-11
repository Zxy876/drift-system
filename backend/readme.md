## drift-backend

独立 FastAPI 后端仓库，提供 Drift 插件调用的核心接口。

### 运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 关键接口

- `POST /ai/intent`
- `POST /world/apply`
- `POST /story/load`
- `POST /story/advance`
- `POST /registry/player-tags`（玩家语义/隐喻备案）
- `POST /poetry/generate`（诗歌 → 场景生成）
- `POST /poetry/command`（插件 `/poem` 命令桥接）

兼容保留：

- `POST /story/load/{player_id}/{level_id}`
- `POST /story/advance/{player_id}`

### Railway

- 入口：`main.py`
- 进程定义：`Procfile`
- 平台配置：`railway.toml`

必需环境变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`

GitHub Integration 部署步骤：

1. 在 Railway 新建 Project。
2. 选择 `Deploy from GitHub Repo` 并连接 `Zxy876/drift-backend`。
3. Service Root 选择仓库根目录。
4. 在 Variables 中配置上面的 3 个 OpenAI 环境变量。
5. 等待自动部署完成后，访问 `/health` 检查：

```bash
curl https://<your-railway-domain>/health
```

### Poetry 引擎（插件接入）

目标链路：

`隐喻备案` → `诗歌输入` → `场景生成(world_patch.mc.build_multi)`

#### 1) 玩家隐喻备案

```bash
curl -X POST https://<your-domain>/registry/player-tags \
	-H 'Content-Type: application/json' \
	-d '{"player":"alice","tag":"moon","resource":"minecraft:lantern"}'
```

#### 2) 插件执行 `/poem`

玩家在 MC 输入：

`/poem 月光照在雾里的船`

插件可直接调用：

```bash
curl -X POST https://<your-domain>/poetry/command \
	-H 'Content-Type: application/json' \
	-d '{"player_id":"alice","command":"/poem 月光照在雾里的船"}'
```

也可调用：`POST /poetry/generate`（传 `poem` 字段）。

#### 3) 插件执行 world_patch

后端返回 `world_patch.mc`，重点字段：

- `build_multi`
- `spawn_multi`
- `blocks`
- `structure`

插件按现有执行器顺序消费这些动作，即可把诗歌转成世界构建。

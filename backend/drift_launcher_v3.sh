#!/usr/bin/env bash
cd "$(dirname "$0")"

echo "============================================"
echo "✨ DriftSystem 启动器 v3 — 真·一键启动版"
echo "============================================"

# 路径定义
PLUGIN_SRC="../mc_plugin"
PLUGIN_TARGET="./server/plugins"
PLUGIN_JAR_NAME="mc_plugin.jar"

BACKEND_PORT=8000
MC_PORT=25565

# -----------------------------
# 🧹 1. 清理残留进程
# -----------------------------
echo "🧹 清理残留的进程 (uvicorn / paper)..."

# 杀掉 uvicorn
lsof -ti :$BACKEND_PORT | xargs kill -9 2>/dev/null

# 杀掉 paper
lsof -ti :$MC_PORT | xargs kill -9 2>/dev/null

# 删除世界锁文件
rm -f ./server/world/session.lock

echo "✔ 进程清理完毕"


# -----------------------------
# 🔧 2. 自动编译 Minecraft 插件
# -----------------------------
echo ""
echo "🔧 检查并编译 Minecraft 插件 (Maven)..."

if [ ! -d "$PLUGIN_SRC" ]; then
    echo "❌ 未找到插件源码目录 $PLUGIN_SRC"
    exit 1
fi

cd "$PLUGIN_SRC"

echo "➡️ 运行 mvn package..."
mvn -q clean package

if [ $? -ne 0 ]; then
    echo "❌ Maven 构建失败"
    exit 1
fi

# 找到 jar
BUILT_JAR=$(ls target/*.jar | head -n 1)

if [ ! -f "$BUILT_JAR" ]; then
    echo "❌ 构建成功但未找到 JAR 文件"
    exit 1
fi

echo "✔ 插件构建成功：$BUILT_JAR"

cd - >/dev/null


# -----------------------------
# 📦 3. 复制插件到 MC 服务端
# -----------------------------
echo ""
echo "📦 部署插件到 Minecraft 服务器..."

mkdir -p "$PLUGIN_TARGET"

cp "$BUILT_JAR" "$PLUGIN_TARGET/$PLUGIN_JAR_NAME"

echo "✔ 插件部署成功：$PLUGIN_TARGET/$PLUGIN_JAR_NAME"


# -----------------------------
# ⚡ 4. 启动 FastAPI 后端
# -----------------------------
echo ""
echo "⚡ 启动 FastAPI 后端 (port=$BACKEND_PORT)..."

source ./venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port $BACKEND_PORT &
BACKEND_PID=$!

echo "✔ 后端启动 PID=$BACKEND_PID"


# -----------------------------
# 🎮 5. 启动 Minecraft 服务端
# -----------------------------
echo ""
echo "🎮 启动 Minecraft 服务器 (port=$MC_PORT)..."

cd ./server
java -Xms1G -Xmx2G -jar paper.jar nogui &
MC_PID=$!

echo "✔ MC 服务器启动 PID=$MC_PID"


echo ""
echo "============================================"
echo "🎉 DriftSystem已全部启动成功！"
echo "📌 后端：http://localhost:$BACKEND_PORT"
echo "📌 Minecraft：localhost:$MC_PORT"
echo "============================================"

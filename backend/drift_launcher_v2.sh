#!/usr/bin/env bash

# 始终在脚本所在目录执行
cd "$(dirname "$0")"

echo "=========================================="
echo "🚀 DriftSystem Launcher v2"
echo "=========================================="

# 简单日志函数
log() {
  echo "[$(date +%H:%M:%S)] $*"
}

# ---------------------- #
#  1. 清理旧进程 & 锁文件
# ---------------------- #

log "🔍 清理旧的后端进程 (8000)..."
if lsof -t -i :8000 >/dev/null 2>&1; then
  log "⚠️ 检测到已有 uvicorn 进程，占用 8000 端口，正在结束..."
  kill -9 $(lsof -t -i :8000) 2>/dev/null || true
else
  log "✅ 8000 端口空闲"
fi

log "🔍 清理旧的 Minecraft 进程 (25565)..."
if lsof -t -i :25565 >/dev/null 2>&1; then
  log "⚠️ 检测到已有 MC 服务器，占用 25565 端口，正在结束..."
  kill -9 $(lsof -t -i :25565) 2>/dev/null || true
else
  log "✅ 25565 端口空闲"
fi

# 清理 session.lock（在没有 MC 进程的前提下）
if [ -f "server/world/session.lock" ]; then
  if ! lsof "server/world/session.lock" >/dev/null 2>&1; then
    log "🧹 删除残留的 session.lock..."
    rm -f "server/world/session.lock"
  else
    log "❌ session.lock 仍被占用，请手动检查 java 进程"
    exit 1
  fi
fi

# ---------------------- #
#  2. 检查 Python & venv
# ---------------------- #

log "🧪 检查 Python 环境..."
if ! command -v python3 >/dev/null 2>&1; then
  log "❌ 未检测到 python3，请先安装 Python3 再运行。"
  exit 1
fi
log "✅ Python3 已安装"

if [ ! -d "venv" ]; then
  log "🌱 未检测到 venv，正在创建虚拟环境..."
  python3 -m venv venv
else
  log "✅ 虚拟环境已存在"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source venv/bin/activate

log "📦 检查并安装 Python 依赖..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
log "✅ 依赖安装完成"

# ---------------------- #
#  3. 启动 FastAPI 后端
# ---------------------- #

log "🚀 启动 FastAPI 后端 (uvicorn:8000)..."

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!
log "➡️ 后端进程 PID: $BACKEND_PID"

# 给它一点时间启动
sleep 2

if lsof -t -i :8000 >/dev/null 2>&1; then
  log "✅ 后端已监听 8000 端口"
else
  log "❌ 后端启动失败（8000 未监听），请检查日志。"
  exit 1
fi

# 避免脚本退出时后台残留 uvicorn
cleanup() {
  if kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    log "🛑 关闭后端进程 $BACKEND_PID..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# ---------------------- #
#  4. 准备 Minecraft 服务器
# ---------------------- #

SERVER_DIR="server"
JAR_NAME="paper.jar"
PAPER_URL="https://api.papermc.io/v2/projects/paper/versions/1.20.1/builds/150/downloads/paper-1.20.1-150.jar"

log "🧩 检查 Minecraft 服务器目录..."
mkdir -p "$SERVER_DIR"
cd "$SERVER_DIR" || exit 1

if [ ! -f "$JAR_NAME" ]; then
  log "⬇️ 未检测到 $JAR_NAME，正在下载 Paper 1.20.1..."
  curl -L -o "$JAR_NAME" "$PAPER_URL"
  log "✅ Paper 下载完成"
else
  log "✅ 已存在 $JAR_NAME，跳过下载"
fi

# 同意 EULA
if [ ! -f "eula.txt" ]; then
  log "📝 创建 eula.txt..."
  echo "eula=true" > eula.txt
else
  log "✅ eula.txt 已存在"
fi

# ---------------------- #
#  5. 自动安装插件 mc_plugin.jar
# ---------------------- #

log "🧩 自动部署 mc_plugin.jar..."

mkdir -p plugins

PLUGIN_TARGET="plugins/mc_plugin.jar"
SRC1="../mc_plugin/target/mc_plugin.jar"
SRC2="../system/mc_plugin/target/mc_plugin.jar"

if [ -f "$SRC1" ]; then
  cp "$SRC1" "$PLUGIN_TARGET"
  log "✅ 已从 $SRC1 复制插件到 $PLUGIN_TARGET"
elif [ -f "$SRC2" ]; then
  cp "$SRC2" "$PLUGIN_TARGET"
  log "✅ 已从 $SRC2 复制插件到 $PLUGIN_TARGET"
else
  log "⚠️ 未找到 mc_plugin.jar（请先在 mc_plugin 目录运行 mvn package）"
fi

# ---------------------- #
#  6. 启动 Minecraft 服务器（前台）
# ---------------------- #

log "🎮 启动 Paper 服务器 (25565)..."
java -Xms2G -Xmx4G -jar "$JAR_NAME" nogui

# 当 Java 退出时，trap 会触发 cleanup 关闭后端
log "🏁 Minecraft 服务器已退出，DriftSystem 后端也将关闭。"

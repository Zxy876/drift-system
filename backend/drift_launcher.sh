#!/bin/bash

echo ""
echo "=========================================="
echo "🚀 DriftSystem Launcher (一键启动器)"
echo "=========================================="
echo ""

# ---------------------- #
#  1. 检查 Python 环境
# ---------------------- #

echo "�� 检查 Python 环境..."

if ! command -v python3 &> /dev/null
then
    echo "❌ 未检测到 python3"
    echo "➡️ 请安装 Python3.10+ 后再次运行"
    exit 1
fi

echo "✔ Python 环境 OK"

# ---------------------- #
#  2. 检查虚拟环境
# ---------------------- #

if [ ! -d "venv" ]; then
    echo "🌱 未检测到 venv，正在创建虚拟环境..."
    python3 -m venv venv
fi

echo "✔ 虚拟环境已准备"

source venv/bin/activate

# ---------------------- #
#  3. 安装依赖
# ---------------------- #

echo "🔍 检查依赖 requirements.txt..."

pip install --upgrade pip >/dev/null

pip install -r requirements.txt

echo "✔ Python 依赖安装完成"

# ---------------------- #
#  4. 启动 Backend
# ---------------------- #

echo ""
echo "🚀 启动 FastAPI 后端..."
echo ""

uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "✔ 后端进程 PID: $BACKEND_PID"

# ---------------------- #
#  5. Minecraft 服务端自动检查
# ---------------------- #

SERVER_DIR="./server"
JAR_NAME="paper.jar"
PAPER_URL="https://api.papermc.io/v2/projects/paper/versions/1.20.1/builds/150/downloads/paper-1.20.1-150.jar"

echo ""
echo "🧩 检查 Minecraft 服务端..."

if [ ! -d "$SERVER_DIR" ]; then
    echo "📁 未检测到 server 目录，自动创建..."
    mkdir $SERVER_DIR
fi

cd $SERVER_DIR

if [ ! -f "$JAR_NAME" ]; then
    echo "⬇️ 未检测到 $JAR_NAME，正在下载 Paper..."
    curl -o $JAR_NAME $PAPER_URL
    echo "✔ Paper 下载完成"
fi

# ---------------------- #
#  6. 自动接受 EULA
# ---------------------- #

if [ ! -f "eula.txt" ]; then
    echo "eula=true" > eula.txt
fi

# ---------------------- #
#  7. 自动安装插件
# ---------------------- #

echo ""
echo "🧩 自动部署 mc_plugin.jar..."

mkdir -p plugins

if [ -f "../../mc_plugin/target/mc_plugin.jar" ]; then
    cp ../../mc_plugin/target/mc_plugin.jar ./plugins/
    echo "✔ 插件已安装"
else
    echo "⚠️ 未找到 mc_plugin.jar（请先 mvn package）"
fi

# ---------------------- #
#  8. 启动 Minecraft 服务端
# ---------------------- #

echo ""
echo "🎮 正在启动 Minecraft 服务端..."
echo ""

java -Xms2G -Xmx4G -jar $JAR_NAME nogui &
MC_PID=$!

echo "✔ MC 已启动，PID: $MC_PID"
echo ""

# ---------------------- #
#  9. 完成提示
# ---------------------- #

echo "=========================================="
echo "✨ DriftSystem 已全部启动成功!"
echo "后端运行端口: http://localhost:8000"
echo "Minecraft 正在运行（localhost）"
echo "=========================================="
echo ""

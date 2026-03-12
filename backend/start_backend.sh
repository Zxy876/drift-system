#!/bin/bash

set -e

echo "=============================="
echo "🚀 启动 DriftSystem 后端 (FastAPI)"
echo "=============================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 端口占用检测/清理
BACKEND_PORT=8000
if command -v lsof >/dev/null 2>&1; then
    EXISTING_PIDS=$(lsof -ti tcp:$BACKEND_PORT 2>/dev/null || true)
    if [ -n "$EXISTING_PIDS" ]; then
        echo "⚠️ 端口 $BACKEND_PORT 已被占用，尝试结束相关进程: $EXISTING_PIDS"
        while read -r PID; do
            [ -z "$PID" ] && continue
            kill "$PID" 2>/dev/null || true
        done <<< "$EXISTING_PIDS"
        sleep 1
        STILL_ALIVE=$(lsof -ti tcp:$BACKEND_PORT 2>/dev/null || true)
        if [ -n "$STILL_ALIVE" ]; then
            echo "⚠️ 进程未完全退出，执行强制结束: $STILL_ALIVE"
            while read -r PID; do
                [ -z "$PID" ] && continue
                kill -9 "$PID" 2>/dev/null || true
            done <<< "$STILL_ALIVE"
            sleep 1
        fi
    fi
fi

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到 python3，请先安装 Python3."
    exit 1
fi

# 检查虚拟环境
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "⬇️ 未检测到 venv，正在创建 ..."
    python3 -m venv "$VENV_DIR"
fi

# 激活虚拟环境
echo "📦 激活虚拟环境 venv ..."
source "$VENV_DIR/bin/activate"

# 安装依赖
echo "📦 正在安装依赖 ..."
pip install -r requirements.txt

# 清理历史 PID 文件
PID_FILE="$SCRIPT_DIR/backend.pid"
[ -f "$PID_FILE" ] && rm -f "$PID_FILE"

# 启动 FastAPI
echo "🌐 后端启动中： http://127.0.0.1:8000"
echo "（按 Ctrl+C 关闭）"
uvicorn app.main:app --reload --host 127.0.0.1 --port "$BACKEND_PORT" &
UVICORN_PID=$!
echo $UVICORN_PID > "$PID_FILE"
wait $UVICORN_PID

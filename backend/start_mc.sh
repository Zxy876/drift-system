#!/bin/bash

echo "=============================="
echo "🎮 启动 DriftSystem MC 服务端"
echo "=============================="

cd "$(dirname "$0")/server"

# 清理上一轮遗留的 PID 和世界锁文件，避免 SessionLock 异常
if [ -f "server.pid" ]; then
    OLD_PID=$(cat server.pid 2>/dev/null)
    if [ -n "$OLD_PID" ] && ps -p "$OLD_PID" >/dev/null 2>&1; then
        echo "❌ 检测到已有运行中的 MC 服务 (PID: $OLD_PID)，请先停止它。"
        exit 1
    fi
    rm -f server.pid
fi

find world world_nether world_the_end -maxdepth 1 -name session.lock -exec rm -f {} + 2>/dev/null

# 端口占用检测/清理
MC_PORT=25565
if command -v lsof >/dev/null 2>&1; then
    OCCUPIED_PIDS=$(lsof -ti tcp:$MC_PORT 2>/dev/null || true)
    if [ -n "$OCCUPIED_PIDS" ]; then
        echo "⚠️ 端口 $MC_PORT 已被占用，尝试结束相关进程: $OCCUPIED_PIDS"
        while read -r PID; do
            [ -z "$PID" ] && continue
            kill "$PID" 2>/dev/null || true
        done <<< "$OCCUPIED_PIDS"
        sleep 1
        STILL_OCCUPIED=$(lsof -ti tcp:$MC_PORT 2>/dev/null || true)
        if [ -n "$STILL_OCCUPIED" ]; then
            echo "⚠️ 进程未完全退出，执行强制结束: $STILL_OCCUPIED"
            while read -r PID; do
                [ -z "$PID" ] && continue
                kill -9 "$PID" 2>/dev/null || true
            done <<< "$STILL_OCCUPIED"
            sleep 1
        fi
    fi
fi

# 自动检测 jar 文件（Paper / Spigot / 其他）
JAR_FILE=$(ls | grep -E "paper|spigot|server.*\.jar" | head -n 1)

if [ -z "$JAR_FILE" ]; then
    echo "❌ 未找到 Minecraft 服务器 JAR 文件（paper/spigot）"
    exit 1
fi

echo "🔍 检测到服务器文件: $JAR_FILE"
echo "🧩 插件目录: plugins/"

# 检查插件是否存在
if [ ! -d "plugins" ]; then
    echo "⚠️ plugins 文件夹不存在，正在创建 ..."
    mkdir plugins
fi

echo "🚀 MC 服务器启动中..."
echo "（按 Ctrl+C 关闭）"

java -Xms2G -Xmx4G -jar "$JAR_FILE" nogui

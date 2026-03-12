#!/bin/bash
echo "====================================="
echo "✨ DriftSystem 一键启动工具"
echo "====================================="
echo "1) 启动后端（FastAPI）"
echo "2) 启动 Minecraft 服务端"
echo "3) 同时启动（分窗口）"
echo "4) 自动安装 Minecraft 服务器（Paper）"
echo "-------------------------------------"
read -p "请选择启动模式: " mode

case $mode in
  1)
    ./start_backend.sh
    ;;
  2)
    ./start_mc.sh
    ;;
  3)
    echo "⚡ 同时启动后端和 MC..."
    ./start_backend.sh &
    ./start_mc.sh &
    ;;
  4)
    ./install_mc.sh
    ;;
  *)
    echo "❌ 无效选择"
    ;;
esac
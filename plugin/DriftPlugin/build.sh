#!/bin/bash

# =========================================
# DriftSystem MC插件构建脚本
# =========================================

set -e

echo "========================================="
echo "  DriftSystem 插件构建"
echo "========================================="

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${BLUE}📦 清理旧构建...${NC}"
mvn clean

echo -e "${BLUE}🔨 开始构建...${NC}"
mvn package

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 构建成功！${NC}"
    
    # 查找生成的jar文件
    JAR_FILE=$(find target -type f -name "*.jar" \
        ! -name "original-*.jar" \
        ! -name "*-sources.jar" \
        ! -name "*-javadoc.jar" | head -1)
    
    if [ -n "$JAR_FILE" ]; then
        echo -e "${GREEN}📄 生成的JAR: ${JAR_FILE}${NC}"
        
        # 显示文件大小
        SIZE=$(du -h "$JAR_FILE" | cut -f1)
        echo -e "${GREEN}📊 文件大小: ${SIZE}${NC}"
        
        # 复制到服务器plugins目录（如果存在）
        SERVER_PLUGINS="../../backend/server/plugins"
        if [ -d "$SERVER_PLUGINS" ]; then
            echo -e "${BLUE}📋 复制到服务器...${NC}"
            cp "$JAR_FILE" "$SERVER_PLUGINS/DriftSystem.jar"
            echo -e "${GREEN}✅ 已复制到: $SERVER_PLUGINS/DriftSystem.jar${NC}"
        fi
        
        # 也复制到根目录server/plugins（如果存在）
        ROOT_SERVER_PLUGINS="../../server/plugins"
        if [ -d "$ROOT_SERVER_PLUGINS" ]; then
            echo -e "${BLUE}📋 复制到根服务器...${NC}"
            cp "$JAR_FILE" "$ROOT_SERVER_PLUGINS/DriftSystem.jar"
            echo -e "${GREEN}✅ 已复制到: $ROOT_SERVER_PLUGINS/DriftSystem.jar${NC}"
        fi
    fi
    
    echo ""
    echo -e "${GREEN}=========================================${NC}"
    echo -e "${GREEN}  构建完成！${NC}"
    echo -e "${GREEN}=========================================${NC}"
    echo ""
    echo -e "${YELLOW}下一步:${NC}"
    echo "  1. 确保后端服务已启动 (backend/)"
    echo "  2. 将JAR放入服务器plugins目录"
    echo "  3. 配置config.yml中的backend_url"
    echo "  4. 重启Minecraft服务器"
    echo ""
    
else
    echo -e "${YELLOW}❌ 构建失败${NC}"
    exit 1
fi

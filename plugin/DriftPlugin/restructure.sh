#!/bin/bash

echo "📦 开始自动重建 MC 插件结构..."

BASE="src/main/java/com/driftmc"

# 创建标准目录
mkdir -p $BASE/backend
mkdir -p $BASE/ai
mkdir -p $BASE/dsl
mkdir -p $BASE/story
mkdir -p $BASE/world
mkdir -p src/main/resources

echo "📁 标准目录创建完成。"

# 自动查找并移动 Java 文件
echo "🔍 搜索并移动你的 Java 源码..."

find . -name "*.java" | while read file; do
    # 获取文件名
    name=$(basename "$file")

    # 跳过已在正确路径中的文件
    if [[ "$file" == src/main/java/com/driftmc* ]]; then
        continue
    fi

    # 根据文件名判断应该放哪里
    case $name in
        DriftMCPlugin.java)
            mv "$file" "$BASE/"
            echo "→ 放入：root: DriftMCPlugin.java"
            ;;
        BackendClient.java)
            mv "$file" "$BASE/backend/"
            echo "→ BackendClient.java → backend/"
            ;;
        PlayerChatListener.java)
            mv "$file" "$BASE/ai/"
            echo "→ PlayerChatListener.java → ai/"
            ;;
        AiClient.java | AiRouterBridge.java)
            mv "$file" "$BASE/ai/"
            echo "→ AI 相关类 → ai/"
            ;;
        DslEngine.java | DslCommands.java)
            mv "$file" "$BASE/dsl/"
            echo "→ DSL 类 → dsl/"
            ;;
        StoryBridge.java)
            mv "$file" "$BASE/story/"
            echo "→ StoryBridge.java → story/"
            ;;
        WorldActions.java)
            mv "$file" "$BASE/world/"
            echo "→ WorldActions.java → world/"
            ;;
        *)
            # 默认放到 com/driftmc 根目录
            mv "$file" "$BASE/"
            echo "→ 未分类：$name → root/"
            ;;
    esac
done

echo "📄 移动 plugin.yml..."
# 搜索 plugin.yml
plugin_file=$(find . -name "plugin.yml" | head -n 1)

if [[ -n "$plugin_file" ]]; then
    mv "$plugin_file" src/main/resources/
    echo "→ plugin.yml 已放入 src/main/resources/"
else
    echo "⚠️ 未找到 plugin.yml，你可能需要手动创建。"
fi

echo "🎉 重建结构完成！"
echo "现在你的 mc_plugin 已经被整理成标准结构啦！"

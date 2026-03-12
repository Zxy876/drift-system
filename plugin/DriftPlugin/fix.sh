#!/bin/bash

set -e

echo "=== DriftSystem 一键修复开始 ==="

PLUGIN_SRC="DriftSystem/system/mc_plugin/src/main/java/com/driftmc"

# 1) 清空 Maven 项目 src/main/java/com/driftmc
echo "[1] 清空 mc_plugin/src/main/java/com/driftmc ..."
rm -rf DriftSystem/system/mc_plugin/src/main/java/com
mkdir -p DriftSystem/system/mc_plugin/src/main/java/com/driftmc

# 2) 把所有 Java 文件移进去
echo "[2] 移动所有 Java 文件到 Maven 项目 ..."
find DriftSystem -type f -name "*.java" \
    ! -path "*/system/mc_plugin/*" \
    -exec mv {} DriftSystem/system/mc_plugin/src/main/java/com/driftmc/ \;

# 3) 删除重复文件 LevelCommand
echo "[3] 删除重复 LevelCommand ..."
find DriftSystem/system/mc_plugin/src/main/java/com/driftmc -type f -name "LevelCommand*.java" | sed -n '2,$p' | xargs -I {} rm {}

# 4) 补 org.json 依赖到 pom.xml
POM="DriftSystem/system/mc_plugin/pom.xml"

echo "[4] 确保 pom.xml 已包含 org.json 依赖 ..."
if ! grep -q "org.json" "$POM"; then
cat >> "$POM" <<EOF

    <dependencies>
        <dependency>
            <groupId>org.json</groupId>
            <artifactId>json</artifactId>
            <version>20240303</version>
        </dependency>
    </dependencies>

EOF
fi

# 5) Maven 构建
echo "[5] 运行 Maven clean package ..."
cd DriftSystem/system/mc_plugin
mvn clean package -e

echo "=== 修复完成！JAR 已生成于 target/ ==="
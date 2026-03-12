#!/bin/bash
echo "=== DriftSystem 全自动结构修复开始 ==="

PROJECT_ROOT="$(cd ../../.. && pwd)"
PLUGIN_DIR="$PROJECT_ROOT/system/mc_plugin"
SRC_JAVA="$PLUGIN_DIR/src/main/java"
RESOURCES_DIR="$PLUGIN_DIR/src/main/resources"

echo "[1] 删除 DriftSystem/com 目录的误放 Java 文件 ..."
rm -rf "$PROJECT_ROOT/com"

echo "[2] 清理 mc_plugin/src/main/java/com/driftmc ..."
rm -rf "$SRC_JAVA/com"

mkdir -p "$SRC_JAVA/com"

echo "[3] 移动真正的 Java 文件到 mc_plugin ..."
find "$PROJECT_ROOT" -type f -name "*.java" \
    ! -path "$SRC_JAVA/*" \
    ! -path "$PLUGIN_DIR/target/*" \
    -exec mv {} "$SRC_JAVA" \;

echo "[4] 将所有 Java 文件统一放进 com/driftmc 目录 ..."
mkdir -p "$SRC_JAVA/com/driftmc"
mv "$SRC_JAVA"/*.java "$SRC_JAVA/com/driftmc" 2>/dev/null

echo "[5] 恢复 pom.xml 正常版本 ..."
cat > "$PLUGIN_DIR/pom.xml" <<EOF
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.driftmc</groupId>
    <artifactId>drift-mc-plugin</artifactId>
    <version>1.0-SNAPSHOT</version>

    <dependencies>
        <!-- Spigot / Paper API -->
        <dependency>
            <groupId>org.spigotmc</groupId>
            <artifactId>spigot-api</artifactId>
            <version>1.20.1-R0.1-SNAPSHOT</version>
            <scope>provided</scope>
        </dependency>

        <!-- JSON 依赖 -->
        <dependency>
            <groupId>org.json</groupId>
            <artifactId>json</artifactId>
            <version>20231013</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.11.0</version>
                <configuration>
                    <source>17</source>
                    <target>17</target>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-shade-plugin</artifactId>
                <version>3.5.0</version>
                <executions>
                    <execution>
                        <phase>package</phase>
                        <goals><goal>shade</goal></goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
EOF

echo "[6] 重新构建 ..."
cd "$PLUGIN_DIR"
mvn clean package -e

echo "=== 修复完成！==="

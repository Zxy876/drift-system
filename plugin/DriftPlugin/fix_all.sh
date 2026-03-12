#!/bin/bash
set -e

echo "=== DriftSystem mc_plugin — 完整重建开始 ==="

# 1. 进入 mc_plugin 根目录
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "[DIR] 当前 mc_plugin 目录: $BASE_DIR"

cd "$BASE_DIR"

# -------------------------------
# 2. 删除损坏的 POM
# -------------------------------
if [ -f "$BASE_DIR/DriftSystem/system/mc_plugin/pom.xml" ]; then
    echo "[CLEAN] 删除递归 POM"
    rm -f "$BASE_DIR/DriftSystem/system/mc_plugin/pom.xml"
fi

# -------------------------------
# 3. 重新创建一个正确的 pom.xml
# -------------------------------
echo "[WRITE] 新 pom.xml"

cat > pom.xml << 'EOF'
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">

  <modelVersion>4.0.0</modelVersion>

  <groupId>com.driftmc</groupId>
  <artifactId>drift-mc-plugin</artifactId>
  <version>1.0-SNAPSHOT</version>
  <packaging>jar</packaging>

  <repositories>
    <repository>
      <id>spigot-repo</id>
      <url>https://hub.spigotmc.org/nexus/content/repositories/snapshots/</url>
    </repository>
  </repositories>

  <dependencies>
    <dependency>
      <groupId>org.spigotmc</groupId>
      <artifactId>spigot-api</artifactId>
      <version>1.20.1-R0.1-SNAPSHOT</version>
      <scope>provided</scope>
    </dependency>

    <dependency>
      <groupId>org.json</groupId>
      <artifactId>json</artifactId>
      <version>20240303</version>
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
    </plugins>
  </build>

</project>
EOF

# -------------------------------
# 4. 清空 src/main/java/com/driftmc
# -------------------------------
echo "[CLEAN] 清空 src/main/java/com/driftmc"

mkdir -p src/main/java/com/driftmc
rm -rf src/main/java/com/driftmc/*

# -------------------------------
# 5. 将所有散落的 com/driftmc/*.java 移回正确位置
# -------------------------------
ROOT_DIR="$(cd "$BASE_DIR/../.." && pwd)"

echo "[SEARCH] 查找散落的 Java 文件 ..."

find "$ROOT_DIR" -type f -name "*.java" | while read f; do
    echo "[MOVE] $f"
    cp "$f" "$BASE_DIR/src/main/java/com/driftmc/"
done

# -------------------------------
# 6. 删除重复的 LevelCommand（actions 下那份）
# -------------------------------
echo "[DELETE] 删除重复的 LevelCommand ..."
rm -f src/main/java/com/driftmc/actions/LevelCommand.java || true

# -------------------------------
# 7. 再次编译
# -------------------------------
echo "[MAVEN] mvn clean package"
mvn -e clean package

echo "=== 完整修复成功！插件已可用 ==="

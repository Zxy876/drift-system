#!/usr/bin/env bash
set -e

echo "🧹 Patch #1: 修正 DSL 包名 + 类名大小写..."

# 1) 把 dsl 包从 org.driftsystem 换成 com.driftmc
for f in \
  src/main/java/com/driftmc/dsl/DslCommand.java \
  src/main/java/com/driftmc/dsl/DslExecutor.java \
  src/main/java/com/driftmc/dsl/DslParser.java \
  src/main/java/com/driftmc/dsl/DslRegistry.java \
  src/main/java/com/driftmc/dsl/DslResult.java \
  src/main/java/com/driftmc/dsl/DSLRuntime.java
do
  if [ -f "$f" ]; then
    sed -i '' 's/package org\.driftsystem\.dsl/package com.driftmc.dsl/' "$f" || true
  fi
done

# 2) 修正 public class 名称与文件名一致
#   DslCommand.java 里不再叫 DSLCommand
if [ -f src/main/java/com/driftmc/dsl/DslCommand.java ]; then
  sed -i '' 's/public class DSLCommand/public class DslCommand/' src/main/java/com/driftmc/dsl/DslCommand.java || true
fi

if [ -f src/main/java/com/driftmc/dsl/DslExecutor.java ]; then
  sed -i '' 's/public class DSLExecutor/public class DslExecutor/' src/main/java/com/driftmc/dsl/DslExecutor.java || true
fi

if [ -f src/main/java/com/driftmc/dsl/DslParser.java ]; then
  sed -i '' 's/public class DSLParser/public class DslParser/' src/main/java/com/driftmc/dsl/DslParser.java || true
fi

echo "🧹 Patch #2: commands 里 BackendClient 引用统一到 com.driftmc.backend..."

for f in src/main/java/com/driftmc/commands/*.java; do
  if [ -f "$f" ]; then
    sed -i '' 's/import org\.driftsystem\.api\.BackendClient;/import com.driftmc.backend.BackendClient;/' "$f" || true
  fi
done

echo "🧹 Patch #3: 自定义 DSL 命令包 / 引用修正..."

if [ -d src/main/java/com/driftmc/commands/custom ]; then
  for f in src/main/java/com/driftmc/commands/custom/*.java; do
    # 旧版还在用 org.driftsystem.dsl.commands
    sed -i '' 's/package org\.driftsystem\.dsl\.commands;/package com.driftmc.commands.custom;/' "$f" || true
    sed -i '' 's/import org\.driftsystem\.dsl\./import com.driftmc.dsl./' "$f" || true
  done
fi

echo "🧹 Patch #4: 删除已经废弃的 AiRouter（旧版 entry）..."

rm -f src/main/java/com/driftmc/intent/AiRouter.java || true

echo "🧹 Patch #5: WorldWatcher 去掉老的 org.driftsystem 依赖..."

if [ -f src/main/java/com/driftmc/world/WorldWatcher.java ]; then
  sed -i '' '/org\.driftsystem\.ai/d' src/main/java/com/driftmc/world/WorldWatcher.java || true
  sed -i '' '/org\.driftsystem\.model/d' src/main/java/com/driftmc/world/WorldWatcher.java || true
fi

echo "✅ 基础补丁完成。现在可以重新编译："
echo "   mvn -q -DskipTests clean package"

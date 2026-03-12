#!/bin/bash

echo "🧹 清理并修复 MC 插件结构（旗舰版 C 方案）..."

BASE="src/main/java/com/driftmc"

# 1. 删除第二套旧代码 org.driftsystem（移动到 backup 而不是删）
if [ -d "src/main/java/org/driftsystem" ]; then
    mkdir -p backup_old_code
    mv src/main/java/org/driftsystem backup_old_code/
    echo "→ 旧的 org.driftsystem 已移到 backup_old_code/"
fi

# 2. 创建完整 C 方案目录
mkdir -p $BASE/{ai,intent,dsl,commands,story,world,npc,session,actions,listeners}

echo "📁 目标目录已同步。"

# 3. 自动分类文件规则
move_file() {
    file=$1
    name=$(basename "$file")
    case $name in
        PlayerChatListener.java)
            mv "$file" "$BASE/ai/" ;;
        AiRouter.java|IntentRouter.java)
            mv "$file" "$BASE/intent/" ;;
        IntentType.java|IntentResponse.java)
            mv "$file" "$BASE/intent/" ;;
        BackendClient.java)
            mv "$file" "$BASE/backend/" ;;
        DSL*.java|Dsl*.java)
            mv "$file" "$BASE/dsl/" ;;
        World*.java)
            mv "$file" "$BASE/world/" ;;
        TreeCommand.java|HeartMenuCommand.java|LevelCommand.java|LevelsCommand.java|AdvanceCommand.java|SayToAICommand.java)
            mv "$file" "$BASE/commands/" ;;
        NPC*.java)
            mv "$file" "$BASE/npc/" ;;
        *Session*.java)
            mv "$file" "$BASE/session/" ;;
        *)
            mv "$file" "$BASE/" ;;
    esac
}

# 4. 扫描 com/driftmc 下所有 Java 文件
find src/main/java/com/driftmc -maxdepth 1 -name "*.java" | while read f; do
    move_file "$f"
done

echo "📦 文件分类完成。"

# 5. 自动生成 AI DeepSeek 客户端（如不存在）
AI_CLIENT="$BASE/ai/AiClient.java"

if [ ! -f "$AI_CLIENT" ]; then
    echo "🧠 注入 DeepSeek AI 客户端..."
    cat > "$AI_CLIENT" << 'EOF'
package com.driftmc.ai;

import okhttp3.*;
import org.bukkit.Bukkit;
import java.util.concurrent.*;
import java.io.IOException;

public class AiClient {

    private final OkHttpClient client;
    private final String apiKey;
    private final String apiUrl = "https://api.deepseek.com/chat/completions";

    public AiClient(String apiKey) {
        this.apiKey = apiKey;
        this.client = new OkHttpClient.Builder()
            .connectTimeout(5, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .build();
    }

    public interface Callback {
        void onResponse(String reply);
        void onError(String err);
    }

    public void ask(String prompt, Callback cb) {
        Bukkit.getScheduler().runTaskAsynchronously(
            Bukkit.getPluginManager().getPlugin("DriftMC"),
            () -> callAI(prompt, cb)
        );
    }

    private void callAI(String prompt, Callback cb) {
        try {
            String json = """
            {
                "model": "deepseek-chat",
                "messages": [{"role":"user","content": "%s"}]
            }
            """.formatted(prompt.replace("\"","'"));

            RequestBody body = RequestBody.create(json, MediaType.parse("application/json"));

            Request req = new Request.Builder()
                    .url(apiUrl)
                    .addHeader("Authorization", "Bearer " + apiKey)
                    .post(body)
                    .build();

            try (Response resp = client.newCall(req).execute()) {
                if (!resp.isSuccessful()) {
                    cb.onError("AI错误 " + resp.code());
                    return;
                }
                String result = resp.body().string();
                cb.onResponse(result);
            }
        } catch (Exception e) {
            cb.onError(e.getMessage());
        }
    }
}
EOF
fi

echo "✨ DeepSeek AI 客户端已生成。"

echo "🎉 旗舰版结构完全修复！你现在可以正常编译、启动、开发 C 方案心悦宇宙。"

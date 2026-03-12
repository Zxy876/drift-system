package com.driftmc.ai;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import org.bukkit.plugin.Plugin;

import com.driftmc.intent.IntentResponse;
import com.google.gson.Gson;

import okhttp3.Call;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

/**
 * DeepSeekLLM API Client
 * 完整：异步、安全、自动解析
 */
public class AiClient {

    private final Plugin plugin;
    private final OkHttpClient http;
    private final Gson gson = new Gson();

    private final String apiKey;
    private final String endpoint = "https://api.deepseek.com/v1/chat/completions";

    public interface Callback {
        void onSuccess(IntentResponse resp);
        void onError(String error);
    }

    public AiClient(Plugin plugin, String apiKey) {
        this.plugin = plugin;
        this.apiKey = apiKey;

        this.http = new OkHttpClient.Builder()
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(20, TimeUnit.SECONDS)
                .build();
    }

    public Plugin getPlugin() { return plugin; }


    /**
     *发送玩家消息 → DeepSeek → IntentResponse
     */
    public void sendToDeepSeek(String playerId, String text, Callback cb) {
        // ------ 构造提示词（最关键） -------
        String systemPrompt = """
            你是 DriftSystem 的 AI 事件推理器。

            输入：玩家的一句自然语言
            输出：严格 JSON，格式为：

            {
              "intent": "story | world | npc | dsl | chat | unknown",
              "command": "...根据意图生成的具体动作...",
              "reply": "AI对玩家说的话",
              "confidence": 0.0 ~ 1.0
            }

            规则：
            - 必须返回 JSON，不要加文字
            - 不要解释
            - intent 必须是明确之一。
        """;

        RequestBody body = RequestBody.create(
            MediaType.parse("application/json"),
            gson.toJson(new ChatRequest(systemPrompt, text))
        );

        Request req = new Request.Builder()
                .url(endpoint)
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .post(body)
                .build();

        // 异步执行请求
        http.newCall(req).enqueue(new okhttp3.Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                cb.onError("网络错误：" + e.getMessage());
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                if (!response.isSuccessful()) {
                    cb.onError("HTTP错误: " + response.code());
                    return;
                }

                String json = response.body().string();

                try {
                    // 解析 DeepSeek 输出并提取 JSON
                    IntentResponse resp = IntentResponse.parse(json);
                    cb.onSuccess(resp);

                } catch (Exception ex) {
                    cb.onError("解析失败：" + ex.getMessage() + "\n原始：" + json);
                }
            }
        });
    }


    // ====== Inner Model for Request ======
    static class ChatRequest {
        final Message[] messages;

        ChatRequest(String systemPrompt, String userText) {
            messages = new Message[]{
                new Message("system", systemPrompt),
                new Message("user", userText)
            };
        }
    }

    static class Message {
        final String role;
        final String content;

        Message(String role, String content) {
            this.role = role;
            this.content = content;
        }
    }
}
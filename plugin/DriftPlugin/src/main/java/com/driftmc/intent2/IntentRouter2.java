package com.driftmc.intent2;

import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import org.bukkit.plugin.java.JavaPlugin;

import com.driftmc.backend.BackendClient;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.Response;

public class IntentRouter2 {

    private static final Gson GSON = new Gson();
    private final JavaPlugin plugin;
    private final BackendClient backend;

    public IntentRouter2(JavaPlugin plugin, BackendClient backend) {
        this.plugin = plugin;
        this.backend = backend;
    }

    /**
     * 多意图解析版本
     * 后端返回 { status, intents: [] }
     * 回调会接收到 IntentResponse2 的列表
     */
    public void askIntent(String playerId, String text, Consumer<List<IntentResponse2>> callback) {
        Map<String, Object> body = new HashMap<>();
        body.put("player_id", playerId);
        body.put("text", text);

        String jsonBody = GSON.toJson(body);

        backend.postJsonAsync("/ai/intent", jsonBody, new Callback() {

            @Override
            public void onFailure(Call call, IOException e) {
                plugin.getLogger().warning("[IntentRouter2] 请求失败: " + e.getMessage());
                List<IntentResponse2> fallback = new ArrayList<>();
                fallback.add(new IntentResponse2(
                    IntentType2.UNKNOWN, null, null, text, null, null, null));
                callback.accept(fallback);
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                try (response) {
                    String resp = response.body() != null ? response.body().string() : "{}";
                    JsonObject root = JsonParser.parseString(resp).getAsJsonObject();

                    List<IntentResponse2> intents = new ArrayList<>();

                    if (root.has("intents") && root.get("intents").isJsonArray()) {
                        JsonArray arr = root.getAsJsonArray("intents");
                        for (int i = 0; i < arr.size(); i++) {
                            JsonObject intentObj = arr.get(i).getAsJsonObject();
                            IntentResponse2 parsed = IntentResponse2.fromJson(intentObj);
                            intents.add(parsed);
                        }
                    }

                    if (intents.isEmpty()) {
                        intents.add(new IntentResponse2(
                                IntentType2.UNKNOWN, null, null, text, null, null, null));
                    }

                    callback.accept(intents);

                } catch (Exception ex) {
                    plugin.getLogger().warning("[IntentRouter2] 解析错误: " + ex.getMessage());
                    List<IntentResponse2> fallback = new ArrayList<>();
                    fallback.add(new IntentResponse2(
                            IntentType2.UNKNOWN, null, null, text, null, null, null));
                    callback.accept(fallback);
                }
            }
        });
    }
}
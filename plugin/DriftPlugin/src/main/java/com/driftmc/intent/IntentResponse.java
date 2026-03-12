package com.driftmc.intent;

import com.google.gson.Gson;

public class IntentResponse {
    private static final Gson gson = new Gson();

    public String intent = "chat";
    public String reply  = "";
    public String command = "";

    /** DeepSeek 返回 JSON → 解析 */
    public static IntentResponse parse(String json) {
        try {
            return gson.fromJson(json, IntentResponse.class);
        } catch (Exception e) {
            IntentResponse r = new IntentResponse();
            r.intent = "chat";
            r.reply = "（AI 返回格式错误）";
            return r;
        }
    }
}
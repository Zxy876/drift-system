package com.driftmc.dsl;

import java.util.Map;

import com.google.gson.Gson;

public class DslParser {

    private static final Gson gson = new Gson();

    public static DslRuntime parse(String json) {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = gson.fromJson(json, Map.class);

            String type = (String) map.get("type");
            @SuppressWarnings("unchecked")
            Map<String, Object> args = (Map<String, Object>) map.get("args");

            return new DslRuntime(type, args);
        } catch (Exception e) {
            return null;
        }
    }
}
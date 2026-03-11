package com.driftmc.backend;

import java.io.IOException;
import java.time.Duration;
import java.util.Map;

import org.bukkit.Bukkit;

import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

public class BackendClient {

    private final String baseUrl;
    private final OkHttpClient client;

    public BackendClient(String baseUrl) {
        this(
                baseUrl,
                Duration.ofSeconds(150),
                Duration.ofSeconds(10),
                Duration.ofSeconds(120),
                Duration.ofSeconds(120));
    }

    public BackendClient(
            String baseUrl,
            Duration callTimeout,
            Duration connectTimeout,
            Duration readTimeout,
            Duration writeTimeout) {

        // ---- Base URL 修正 ----
        if (baseUrl.endsWith("/")) {
            baseUrl = baseUrl.substring(0, baseUrl.length() - 1);
        }
        this.baseUrl = baseUrl;

        // ---- 最终稳定配置（适配 DriftSystem） ----
        this.client = new OkHttpClient.Builder()
                .callTimeout(callTimeout) // 整体最大时间
                .connectTimeout(connectTimeout) // 连接服务器超时
                .readTimeout(readTimeout) // 读取 JSON 超时
                .writeTimeout(writeTimeout) // 发送 JSON 超时
                .retryOnConnectionFailure(true) // 避免偶发超时
                .followRedirects(true)
                .build();
    }

    private String buildUrl(String path) {
        if (!path.startsWith("/"))
            path = "/" + path;
        return baseUrl + path;
    }

    // ------------------------------------------------------
    // 同步 postJson（调试用）
    // ------------------------------------------------------
    public String postJson(String path, String json) throws IOException {
        if (Bukkit.getServer() != null && Bukkit.isPrimaryThread()) {
            throw new IllegalStateException("BackendClient.postJson cannot run on the primary server thread");
        }
        RequestBody body = RequestBody.create(
                MediaType.parse("application/json; charset=utf-8"),
                json);

        Request request = new Request.Builder()
                .url(buildUrl(path))
                .post(body)
                .build();

        try (Response resp = client.newCall(request).execute()) {
            if (!resp.isSuccessful()) {
                throw new IOException("POST " + path + " failed: " + resp.code());
            }
            ResponseBody rb = resp.body();
            return rb != null ? rb.string() : "";
        }
    }

    // ------------------------------------------------------
    // 异步 postJson（用于 IntentRouter2）
    // ------------------------------------------------------
    public void postJsonAsync(String path, String json, Callback callback) {

        RequestBody body = RequestBody.create(
                MediaType.parse("application/json; charset=utf-8"),
                json);

        Request request = new Request.Builder()
                .url(buildUrl(path))
                .post(body)
                .build();

        client.newCall(request).enqueue(callback);
    }

    // ------------------------------------------------------
    // 异步 GET 请求（用于获取小地图等资源）
    // ------------------------------------------------------
    public void getAsync(String path, Callback callback) {
        Request request = new Request.Builder()
                .url(buildUrl(path))
                .get()
                .build();

        client.newCall(request).enqueue(callback);
    }

    public void getAsync(String path, Map<String, String> headers, Callback callback) {
        Request.Builder builder = new Request.Builder()
                .url(buildUrl(path))
                .get();

        if (headers != null) {
            headers.forEach((key, value) -> {
                if (key != null && value != null) {
                    builder.addHeader(key, value);
                }
            });
        }

        Request request = builder.build();

        client.newCall(request).enqueue(callback);
    }

    public String getBaseUrl() {
        return baseUrl;
    }
}
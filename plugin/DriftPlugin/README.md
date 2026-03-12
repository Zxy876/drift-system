# Drift AI Narrative Engine for Minecraft

Drift AI Narrative Engine 是一个 Paper 插件，负责把玩家聊天桥接到 Drift 后端（FastAPI），并把返回的 `world_patch` 执行到 Minecraft 世界。

## Required Minecraft Version

- Paper `1.20.1+`
- Java `17+`

## Installation

1. 构建插件：

   ```bash
   mvn clean package
   cp target/mc_plugin-1.0-SNAPSHOT.jar target/drift-plugin.jar
   ```

2. 将 `target/drift-plugin.jar` 放入服务器 `plugins/` 目录。
3. 启动一次服务器，让插件生成默认配置文件。
4. 修改 `plugins/DriftSystem/config.yml` 的后端地址。
5. 重启服务器。

## config.yml

核心配置如下：

```yaml
backend_url: "https://drift-backend-production-c2a5.up.railway.app"

system:
  debug: false
  backend_call_timeout: 150
  backend_connect_timeout: 10
  backend_read_timeout: 120
  backend_write_timeout: 120
```

## backend_url Setup

- `backend_url` 必须是可公网访问的 Drift backend（Railway）地址。
- 插件内所有后端 HTTP 请求都通过该配置初始化的 `BackendClient` 发送。
- 当 `backend_url` 为空时，插件会直接禁用，避免误连本地地址。

## Backend API Compatibility

插件联调使用以下接口：

- `POST /ai/intent`
- `POST /world/apply`
- `POST /story/load`
- `POST /story/advance`

## Debug Logging

插件已内置三类调试日志：

- `intent request`：请求 `/ai/intent` 时记录 payload 预览
- `world patch response`：请求 `/world/apply` 时记录响应预览
- `http error`：HTTP 失败或非 2xx 响应时记录错误信息

可在服务器控制台中按 `BackendClient` 关键字过滤查看。
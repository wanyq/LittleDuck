# HTTP 请求响应示例

以下 Cookie、Key、ID 和模型名均为演示值，不是可用凭据。

## 1. 注册并建立用户会话

```http
POST /api/v1/user/auth/register
Origin: https://littleduck.example
Content-Type: application/json

{"phone":"13800138000","verificationCode":"000000"}
```

```http
HTTP/1.1 201 Created
Set-Cookie: ld_user_session=<opaque>; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/user
Content-Type: application/json

{
  "user": {
    "id": "8c3359aa-49a8-4493-ad2d-302a9b36a59d",
    "phone": "13800138000",
    "createdAt": "2026-07-16T12:00:00Z"
  },
  "expiresAt": "2026-07-23T12:00:00Z"
}
```

## 2. 新对话并流式生成

```http
POST /api/v1/user/generations
Origin: https://littleduck.example
Accept: text/event-stream
Content-Type: application/json
Cookie: ld_user_session=<opaque>

{
  "clientMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
  "content": "帮我写一个 Python 脚本"
}
```

`clientMessageId` 由浏览器生成一次并随同一消息的网络重试复用。完整成功、失败和停止
流分别见 `sse-chat-success.txt`、`sse-chat-failure.txt` 和 `sse-chat-stopped.txt`。

## 3. 重复提交恢复已有状态

同一用户重复提交相同 `clientMessageId`：

```http
HTTP/1.1 409 Conflict
Content-Type: application/json

{
  "error": {
    "code": "DUPLICATE_MESSAGE",
    "message": "该消息已经提交，请读取已有生成状态",
    "requestId": "req_01",
    "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca"
  }
}
```

客户端随后读取权威状态：

```http
GET /api/v1/user/generations/2c255ae2-d891-4d6c-80c5-3d5ee1f534ca
Cookie: ld_user_session=<opaque>
```

如果 `status=streaming`，页面每秒短轮询该端点并显示数据库中的部分内容；如果已经终态，
直接用返回的 `assistantMessage` 收敛 UI。P0 不提供 SSE 事件重放端点。

## 4. 停止

```http
POST /api/v1/user/generations/2c255ae2-d891-4d6c-80c5-3d5ee1f534ca/stop
Origin: https://littleduck.example
Content-Type: application/json
Cookie: ld_user_session=<opaque>
```

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "generation": {
    "id": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
    "conversationId": "6bf22123-6db0-4232-929d-3c77272a6ad2",
    "userMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "assistantMessageId": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "kind": "chat",
    "status": "streaming",
    "stopRequested": true,
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:03Z"
  },
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "conversationId": "6bf22123-6db0-4232-929d-3c77272a6ad2",
    "role": "assistant",
    "status": "generating",
    "content": "已生成的部分内容",
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:03Z"
  }
}
```

重复停止已终态生成返回 HTTP 200 和当前终态，不产生第二个终态事件。

## 5. 重试失败或停止回复

```http
POST /api/v1/user/assistant-messages/4cbe9c70-74ff-4d5c-a70f-131722b21589/retries
Origin: https://littleduck.example
Accept: text/event-stream
Content-Type: application/json
Cookie: ld_user_session=<opaque>

{"clientRetryId":"3aa76721-544d-4f7d-a71f-ad96b2c4fbe8"}
```

响应 `generation.started.kind=retry`；服务复用原用户消息，新增助手消息、generation 和
LLM call。重复 `clientRetryId` 使用与创建消息相同的 `DUPLICATE_MESSAGE` 语义。

## 6. 管理端读取和保存配置

```http
GET /api/v1/admin/llm-config
Cookie: ld_admin_session=<opaque>
```

未配置返回 `{"configured":false,"config":null}`；已配置时，只有已认证管理员能得到完整
明文 Key：

```json
{
  "configured": true,
  "config": {
    "provider": "openai",
    "apiKey": "<mock-plaintext-visible-to-admin>",
    "model": "example-model",
    "updatedAt": "2026-07-16T12:00:00Z"
  }
}
```

数据库只保存 AES-256-GCM 密文和 nonce；明文只在请求处理内存中短暂存在，不记录日志。

## 7. 测试未保存配置

```http
POST /api/v1/admin/llm-config/test
Origin: https://littleduck.example
Cookie: ld_admin_session=<opaque>
Content-Type: application/json

{"provider":"openai","apiKey":"<mock-unsaved-form-value>","model":"example-model"}
```

测试失败仍返回 HTTP 200，表示测试动作已执行；`success=false` 携带管理员可见的供应商
错误。测试值不写配置，也不创建话题 LLM 调用记录。

## 8. 页码分页与实际调用记录

```json
{
  "items": [
    {
      "id": "f8db5c23-360e-420c-bd4d-438e11c29351",
      "step": 1,
      "callType": "chat",
      "relatedMessageId": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
      "provider": "openai",
      "model": "example-model",
      "prompt": [{"role":"user","content":"帮我写一个 Python 脚本"}],
      "responseText": "当然可以。请告诉我脚本要完成什么功能？",
      "status": "succeeded",
      "providerResponseId": "resp_mock",
      "providerError": null,
      "startedAt": "2026-07-16T12:00:00Z",
      "finishedAt": "2026-07-16T12:00:04Z"
    }
  ],
  "page": 1,
  "pageSize": 50,
  "total": 1
}
```

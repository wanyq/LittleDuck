# HTTP 请求响应示例

示例使用占位 Cookie 和 Token，不包含真实凭据。

## 1. 注册

```http
POST /api/v1/user/auth/register
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
  "csrfToken": "<mock-csrf-token-at-least-32-chars>",
  "expiresAt": "2026-07-23T12:00:00Z"
}
```

## 2. 创建新对话并流式生成

```http
POST /api/v1/user/generations
Accept: text/event-stream
Content-Type: application/json
Cookie: ld_user_session=<opaque>
X-CSRF-Token: <mock-csrf-token-at-least-32-chars>
Idempotency-Key: 56d34c5c-7714-47b2-98b8-9c89c695849d

{
  "clientMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
  "content": "帮我写一个 Python 脚本"
}
```

完整 SSE 示例见：

- `sse-chat-success.txt`
- `sse-chat-failure.txt`
- `sse-chat-stopped.txt`

## 3. 恢复第 17 个事件之后的流

```http
GET /api/v1/user/generations/2c255ae2-d891-4d6c-80c5-3d5ee1f534ca/stream?after=17
Accept: text/event-stream
Cookie: ld_user_session=<opaque>
```

如果客户端已经收到终态：

```http
HTTP/1.1 204 No Content
```

## 4. 停止

```http
POST /api/v1/user/generations/2c255ae2-d891-4d6c-80c5-3d5ee1f534ca/stop
Cookie: ld_user_session=<opaque>
X-CSRF-Token: <mock-csrf-token-at-least-32-chars>
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
    "lastEventSequence": 5,
    "cancelRequestedAt": "2026-07-16T12:00:03Z",
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:03Z"
  },
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "conversationId": "6bf22123-6db0-4232-929d-3c77272a6ad2",
    "role": "assistant",
    "status": "generating",
    "content": "已生成的部分内容",
    "replyToMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
    "canRetry": false,
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:03Z"
  }
}
```

## 5. 重试

```http
POST /api/v1/user/assistant-messages/4cbe9c70-74ff-4d5c-a70f-131722b21589/retries
Accept: text/event-stream
Cookie: ld_user_session=<opaque>
X-CSRF-Token: <mock-csrf-token-at-least-32-chars>
Idempotency-Key: 3aa76721-544d-4f7d-a71f-ad96b2c4fbe8
```

响应 `generation.started.kind` 为 `retry`，返回原用户消息和新助手消息。

## 6. 获取管理端配置

```http
GET /api/v1/admin/llm-config
Cookie: ld_admin_session=<opaque>
```

首次未配置：

```json
{"configured":false,"config":null}
```

已配置：

```json
{
  "configured": true,
  "config": {
    "provider": "openai",
    "apiKey": "<plaintext-visible-to-admin>",
    "model": "example-model",
    "updatedAt": "2026-07-16T12:00:00Z"
  }
}
```

## 7. 测试未保存配置

```http
POST /api/v1/admin/llm-config/test
Cookie: ld_admin_session=<opaque>
X-CSRF-Token: <mock-admin-csrf-token-at-least-32-chars>
Content-Type: application/json

{"provider":"openai","apiKey":"<unsaved-form-value>","model":"example-model"}
```

测试失败仍返回 HTTP 200，表示“测试动作完成”；`success=false` 携带管理员可见供应商错误。Schema/认证错误仍使用 4xx。

## 8. 管理端话题调用详情

```json
{
  "items": [
    {
      "id": "f8db5c23-360e-420c-bd4d-438e11c29351",
      "step": 1,
      "callType": "chat",
      "relatedMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
      "provider": "openai",
      "model": "example-model",
      "prompt": [
        {"role": "user", "content": "帮我写一个 Python 脚本"}
      ],
      "responseText": "当然可以。请告诉我脚本要完成什么功能？",
      "status": "succeeded",
      "providerResponseId": "resp_mock",
      "providerError": null,
      "startedAt": "2026-07-16T12:00:00Z",
      "finishedAt": "2026-07-16T12:00:04Z"
    }
  ],
  "nextCursor": null,
  "hasMore": false
}
```

# LittleDuck SSE 流式协议合同

## 1. 适用范围

本合同覆盖：

- 发送首条或后续用户消息并创建聊天生成；
- 对失败或停止的助手消息发起重试；
- 查询生成状态；
- 停止生成；
- 浏览器断线后的事件恢复。

LittleDuck 使用应用级事件，不透传 OpenAI 原始事件。供应商适配器可使用 OpenAI Responses API 的类型化流事件，但前端只依赖本文件定义的 `generation.*`。

## 2. 传输

### 建立新生成

```http
POST /api/v1/user/generations
Accept: text/event-stream
Content-Type: application/json
Idempotency-Key: <uuid-or-random-string>
X-CSRF-Token: <session-csrf-token>
Cookie: ld_user_session=...
```

### 建立重试

```http
POST /api/v1/user/assistant-messages/{assistantMessageId}/retries
Accept: text/event-stream
Idempotency-Key: <new-key>
X-CSRF-Token: <session-csrf-token>
Cookie: ld_user_session=...
```

### 恢复流

```http
GET /api/v1/user/generations/{generationId}/stream?after=17
Accept: text/event-stream
Cookie: ld_user_session=...
```

也可以发送 `Last-Event-ID: 17`；若 header 与 query 同时存在，必须相等，否则返回 `400 VALIDATION_ERROR`。

## 3. 响应头

成功流：

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
```

HTTP 校验失败、未认证、越权或业务冲突发生在流建立前时，返回普通 `application/json` 错误，不返回 SSE。

## 4. 帧格式

持久化业务事件：

```text
id: 18
event: generation.delta
data: {"generationId":"...","sequence":18,"assistantMessageId":"...","delta":"你好","accumulatedLength":42,"occurredAt":"2026-07-16T12:00:00Z"}

```

规则：

- 每个帧以空行结束。
- `data` 是单行 UTF-8 JSON。
- `id` 是当前 generation 内从 1 开始严格递增的十进制整数。
- JSON 的 `sequence` 必须与 `id` 相同。
- 业务事件写入数据库后才能发送，保证恢复可重放。
- 单个 `generation.delta` 可以包含多个供应商 token；服务端建议按 100–250 ms 或 256–512 字符合并。

心跳：

```text
event: heartbeat
data: {"generationId":"...","occurredAt":"2026-07-16T12:00:15Z"}

```

心跳不含 `id`、不持久化、不改变 sequence。建议每 15 秒发送一次。

## 5. 事件类型

### `generation.started`

每个 generation 恰好一次，sequence=1。

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 1,
  "kind": "chat",
  "conversation": {
    "id": "6bf22123-6db0-4232-929d-3c77272a6ad2",
    "title": "帮我写一个 Python 脚本",
    "titleStatus": "temporary",
    "createdAt": "2026-07-16T12:00:00Z",
    "lastActivityAt": "2026-07-16T12:00:00Z"
  },
  "userMessage": {
    "id": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "role": "user",
    "status": "persisted",
    "content": "帮我写一个 Python 脚本",
    "createdAt": "2026-07-16T12:00:00Z"
  },
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "role": "assistant",
    "status": "generating",
    "content": "",
    "replyToMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "createdAt": "2026-07-16T12:00:00Z"
  },
  "occurredAt": "2026-07-16T12:00:00Z"
}
```

继续已有会话时 `conversation` 返回更新后的当前投影。重试时：

- `kind=retry`；
- `userMessage` 是原用户消息；
- `assistantMessage.retryOfMessageId` 指向原失败/停止助手消息。

### `generation.delta`

可出现零到多次。

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 2,
  "assistantMessageId": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
  "delta": "当然可以。",
  "accumulatedLength": 6,
  "occurredAt": "2026-07-16T12:00:01Z"
}
```

客户端只追加 `delta`；`accumulatedLength` 用于检测重复或缺帧，不用于截断 Unicode 字符。

### `generation.completed`

成功终态，恰好一次。

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 9,
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "role": "assistant",
    "status": "completed",
    "content": "当然可以。请告诉我脚本要完成什么功能？",
    "replyToMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:04Z"
  },
  "conversation": {
    "id": "6bf22123-6db0-4232-929d-3c77272a6ad2",
    "title": "帮我写一个 Python 脚本",
    "titleStatus": "temporary",
    "lastActivityAt": "2026-07-16T12:00:04Z"
  },
  "titleGeneration": "queued",
  "occurredAt": "2026-07-16T12:00:04Z"
}
```

该事件发送后立即关闭 SSE。`titleGeneration=queued|not_needed` 只表示后台任务状态；标题生成不阻塞聊天终态。

### `generation.failed`

失败终态，恰好一次。

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 7,
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "role": "assistant",
    "status": "failed",
    "content": "已收到的部分内容",
    "replyToMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:04Z"
  },
  "error": {
    "code": "LLM_UNAVAILABLE",
    "message": "回复生成失败，请稍后重试",
    "retryable": true
  },
  "occurredAt": "2026-07-16T12:00:04Z"
}
```

普通用户事件禁止包含供应商错误、API Key、模型内部请求或堆栈。

### `generation.stopped`

停止终态，恰好一次。

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 7,
  "assistantMessage": {
    "id": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
    "role": "assistant",
    "status": "stopped",
    "content": "已生成的部分内容",
    "replyToMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
    "createdAt": "2026-07-16T12:00:00Z",
    "updatedAt": "2026-07-16T12:00:04Z"
  },
  "stoppedBy": "user",
  "occurredAt": "2026-07-16T12:00:04Z"
}
```

`stoppedBy` 可为 `user` 或 `logout`。

## 6. 顺序和终态

- `started` 必须先于所有 delta 和终态。
- delta 只允许在 started 后、终态前。
- `completed`、`failed`、`stopped` 互斥；每个 generation 只能出现一个终态。
- 终态帧提交数据库后发送；发送后服务端关闭连接。
- 如果连接无终态异常关闭，客户端不得自行把消息标为 failed，应恢复流或查询生成状态。

## 7. 断线恢复

### 已知最后 sequence

客户端记录每个持久化事件的 `id`。重连：

```http
GET /api/v1/user/generations/{generationId}/stream?after=<lastSequence>
```

服务端按顺序重放所有 `sequence > after` 的事件，然后：

- 任务仍活动：继续 tail 新事件；
- 任务已终态：发送尚未收到的终态后关闭；
- `after` 等于终态 sequence：返回 204，无响应体；
- `after` 大于服务端 `lastEventSequence`：400 `CURSOR_INVALID`。

### 未知最后 sequence

不传 `after` 时从 sequence=1 重放。前端应以 generation ID 去重已有 UI。

### 事件过期

流事件至少保留 24 小时。重放材料已清理时返回：

```http
HTTP/1.1 410 Gone
Content-Type: application/json

{
  "error": {
    "code": "STREAM_REPLAY_EXPIRED",
    "message": "流式记录已过期，请刷新会话查看最终状态"
  }
}
```

最终消息、生成状态和 LLM 调用不随事件清理而删除。

### 首次 POST 在收到 started 前断线

客户端使用相同 `Idempotency-Key` 重发完全相同的 POST：

- 请求指纹相同：返回原 generation 的重放/继续流；
- 请求指纹不同：409 `IDEMPOTENCY_KEY_REUSED`。

## 8. 停止语义

```http
POST /api/v1/user/generations/{generationId}/stop
X-CSRF-Token: ...
```

- `queued/streaming`：记录 cancel 请求，返回 202 和当前 generation；最终以 SSE/查询为准。
- `completed/failed/stopped`：幂等返回 200 和现有终态。
- 不属于当前用户或不存在：404。
- stop 返回成功不等于供应商已立即停止；服务端必须在收到取消后尽快终止读取，并以数据库条件更新解决 stop/completed 竞态。

## 9. 页面与网络中断

- 浏览器关闭、Fetch Abort、TCP 断开都不等于用户 stop。
- 服务端继续生成和持久化，除非收到显式 stop、当前 Session 退出、供应商失败或服务端故障。
- 再次进入会话时，先读消息和 generation 权威状态，再决定是否恢复活动流。
- API 进程重启后遗留活动任务被恢复任务标为 failed，并保留部分内容；不会自动重复调用模型。

## 10. Mock 场景

Mock 服务必须至少支持：

| `X-Mock-Scenario` | 行为 |
| --- | --- |
| `chat-success` | started → 多个 delta → completed |
| `chat-failure` | started → delta → failed |
| `chat-stopped` | started → delta → stopped |
| `chat-slow` | started 后每 1 秒一个 delta，并发送 heartbeat |
| `replay-success` | 根据 `after` 重放剩余事件 |
| `disconnect-before-started` | 首次连接关闭，相同幂等键重试后返回原流 |

## 11. 供应商适配说明

OpenAI 官方文档说明 Responses API 可通过 `stream: true` 使用 SSE，并产生类型化语义事件，如创建、文本 delta、完成和错误。LittleDuck adapter 负责：

1. 把供应商文本 delta 合并成 LittleDuck `generation.delta`；
2. 把供应商完成转换成 `generation.completed`；
3. 把供应商或网络错误归一化为 `generation.failed`；
4. 在停止时传递取消信号并保存实际部分返回；
5. 保存实际发送的 Prompt 与实际收到的返回；
6. 不向浏览器暴露供应商事件、API Key、请求头或内部错误。

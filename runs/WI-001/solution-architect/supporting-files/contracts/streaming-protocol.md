# LittleDuck MVP SSE 协议

## 1. 适用范围

以下端点直接返回 SSE：

- `POST /api/v1/user/generations`：新消息；
- `POST /api/v1/user/assistant-messages/{assistantMessageId}/retries`：失败或停止回复重试。

LittleDuck 不向前端透传 OpenAI 事件。当前合同不提供持久化事件重放端点；页面或网络中断
后，通过 generation 和消息查询恢复权威状态。

## 2. 请求建立

请求使用 `fetch()`，因为需要 Cookie、JSON body 和错误状态处理。浏览器生成一次 UUID：

```json
{
  "conversationId": "6bf22123-6db0-4232-929d-3c77272a6ad2",
  "clientMessageId": "d5026980-61a4-4478-a045-bd2efbf17abc",
  "content": "帮我写一个 Python 脚本"
}
```

新对话省略 `conversationId`。网络重试必须复用同一个 `clientMessageId`；409
`DUPLICATE_MESSAGE` 会返回已有 `generationId`，客户端随后查询该生成，不再发送第二条消息。
服务端先 trim `content` 再执行 1..4000 校验；trim 后为空时返回 400，不能创建会话、消息、
generation、LLM call 或打开 SSE。

重试 body 为：

```json
{"clientRetryId":"4a055129-4e14-4624-931f-8f4661bd1232"}
```

## 3. 响应头

成功流：

```http
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache, no-transform
X-Accel-Buffering: no
```

Nginx 对流式路由关闭 buffering 和压缩，并设置大于模型调用超时的读取超时。

## 4. 帧格式

每帧只使用 `event` 和单行 JSON `data`：

```text
event: generation.delta
data: {"generationId":"...","sequence":2,"assistantMessageId":"...","delta":"你好","accumulatedLength":2,"occurredAt":"2026-07-17T03:00:00Z"}

```

SSE `sequence` 只用于单条活连接内检查顺序，从 1 递增；它不同于 Message 的持久化
`sequence`，不能用于断线重放。
未知事件类型必须忽略。收到无法解析的 JSON 时终止本地读取并查询 generation 状态。

## 5. 事件

### `generation.started`

数据库创建事务已经提交后发送，且只发送一次：

```json
{
  "generationId": "2c255ae2-d891-4d6c-80c5-3d5ee1f534ca",
  "sequence": 1,
  "kind": "chat",
  "conversationId": "6bf22123-6db0-4232-929d-3c77272a6ad2",
  "userMessageId": "53396f0a-6840-4990-a66c-3ba83e9c1932",
  "assistantMessageId": "4cbe9c70-74ff-4d5c-a70f-131722b21589",
  "temporaryTitle": "帮我写一个 Python 脚本",
  "occurredAt": "2026-07-17T03:00:00Z"
}
```

### `generation.delta`

零到多个。`delta` 必须至少一个字符且只能追加；provider 的空字符串 chunk 会被忽略，不
写库、不递增 sequence、不发事件。`accumulatedLength` 用于发现客户端渲染异常，不用于恢复。
服务端可以把供应商 token 合并为约 50～100ms 一个 delta，以减少数据库写入和 UI 抖动。

### `generation.completed`

唯一成功终态。包含权威 generation 和 assistantMessage；客户端用完整 assistantMessage 覆盖
本地增量文本。`titleWillBeAttempted` 表示是否会非阻塞尝试正式标题。

### `generation.failed`

唯一失败终态。包含权威 generation、assistantMessage 和公开错误：

```json
{
  "code": "LLM_UNAVAILABLE",
  "message": "回复生成失败，请稍后重试",
  "retryable": true
}
```

失败时助手消息可保留部分内容。供应商详情只进入管理员可见 `llm_calls`。

### `generation.stopped`

唯一停止终态。包含权威 generation、assistantMessage 和 `stoppedBy=user|logout`。显式
`/stop` 仍按当前用户授权；logout 只停止由精确当前 Session 发起的 generation，不影响同
用户其他 Session。停止不删除已生成部分内容。

### `heartbeat`

可选。模型长时间没有 delta 时每 15 秒发送一次，避免中间代理误判空闲。heartbeat 不递增
业务 sequence，也不改变状态。

## 6. 顺序与终态

一条成功建立的流必须满足：

1. 第一条业务事件是 `generation.started`；
2. 随后是零到多个 `generation.delta`；
3. 最后恰好一个 `completed`、`failed` 或 `stopped`；
4. 终态后关闭响应；
5. heartbeat 可穿插，但不能出现在终态之后。

在收到 started 之前发生认证、校验、重复提交或数据库错误时，返回普通 JSON HTTP 错误，
不建立 SSE。started 之后的模型错误必须通过 `generation.failed` 表达，HTTP 状态保持 200。

## 7. 停止

客户端调用：

```http
POST /api/v1/user/generations/{generationId}/stop
```

- streaming 时返回 202，并等待 SSE 或状态查询出现终态；
- 已终态返回 200 和当前状态；
- 不存在或不属于当前用户统一 404；
- 重复停止不得新增消息、生成或调用记录。

输入框在 streaming 时不得再次提交。停止请求后前端不自行伪造 stopped，仍以服务端终态为准。

## 8. 页面、网络和进程中断

### 浏览器断线

SSE 连接关闭只移除订阅者，不直接失败或停止进程内生成任务。客户端保存 started 中的
`generationId`：

1. 重新进入会话时读取会话与最近消息；
2. `GET /api/v1/user/generations/{generationId}` 读取权威状态；
3. 若仍为 streaming，约每秒短轮询；
4. 终态后使用保存的助手完整/部分内容。

这满足 PRD“再次进入会话时以系统最终保存状态展示，不重复生成同一条回复”，而不承担
逐事件持久化、保留和清理成本。

### 首次请求结果未知

如果网络在 started 前中断，客户端使用原 `clientMessageId` 重试。若服务器已经提交事务，
返回 409 和已有 `generationId`；否则正常创建。两种情况都不会产生重复消息。

### 服务进程重启

MVP 不续接供应商流。API 先启动；数据库不可用或遗留收敛未完成时 `/healthz` 返回 503。
恢复器带重试，只把 UTC startup cutoff 前仍为 streaming 的状态写为 failed/
`GENERATION_INTERRUPTED`，保留部分内容并允许重试；cutoff 后的新任务不受影响。服务器服务
恢复与单次模型流续接是两项不同承诺，Mission 只要求前者。

## 9. Mock 场景

`scripts/mock-server.mjs` 支持：

- `chat-success`：started → delta → completed；
- `chat-failure`：started → delta → failed；
- `chat-stopped`：started → delta → stopped；
- `duplicate-message`：409，并返回 existing generationId。

示例文件由 `scripts/check-sse-examples.mjs` 检查 JSON、顺序、递增 sequence 和唯一终态。

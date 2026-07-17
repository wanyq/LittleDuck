# LittleDuck MVP 数据模型

## 1. 原则

- PostgreSQL 是用户、会话、消息、生成、配置和 LLM 调用的唯一权威存储；
- 用户端所有资源查询必须同时带当前 `user_id`；
- 产品状态只保存一次，不增加事件溯源、通用 Job 或 checkpoint 表；
- LLM 调用记录保存实际 Prompt、实际完整/部分返回和供应商错误；
- 时间以 UTC 保存，H5 分组和管理端日期筛选按 Asia/Shanghai 转换；
- P0 不删除数据，业务表长期保留。

## 2. 关系

```text
users 1--N user_sessions
users 1--N conversations
conversations 1--N messages
conversations 1--N generations
conversations 1--N llm_calls
generations 1--1 user message
generations 1--1 assistant message
generations 1--1 chat/retry llm_call
admins 1--N admin_sessions
llm_configs exactly one effective row
```

## 3. 核心表

### `users`

`id`、唯一 `phone`、`created_at`、`updated_at`。验证码固定为产品规则，不保存验证码。

### `user_sessions`

`id`、`user_id`、唯一 `token_hash`、`expires_at`、`revoked_at`、`created_at`。浏览器只持有
原始随机 Token；数据库泄漏不直接暴露有效 Session。

### `admins` / `admin_sessions`

与用户身份域分表。`admins.password_hash` 保存强哈希；Session 结构与用户相同，但 Cookie
名称和 Path 不同。

### `conversations`

| 字段 | 说明 |
| --- | --- |
| `id`, `user_id` | 会话及所有者 |
| `title` | 最多 20 字符 |
| `title_status` | `temporary` / `final` |
| `last_activity_at` | 成功、失败、停止均更新，用于排序与时间分组 |
| `created_at`, `updated_at` | UTC 时间 |

用户会话列表以 `user_id, last_activity_at DESC` 查询；标题搜索仍带 `user_id`。

### `messages`

| 字段 | 说明 |
| --- | --- |
| `id`, `conversation_id` | 消息归属 |
| `role` | `user` / `assistant` |
| `status` | `persisted` / `generating` / `completed` / `failed` / `stopped` |
| `content` | 用户正文或助手完整/部分正文 |
| `reply_to_message_id` | 助手对应的用户消息 |
| `retry_of_message_id` | 新助手消息所重试的旧助手消息，可空 |
| `created_at`, `updated_at` | 顺序和显示时间 |

失败或停止助手消息不覆盖；重试新增一条助手消息。上下文只取 persisted 用户消息与
completed 助手消息的完整轮次。

### `generations`

| 字段 | 说明 |
| --- | --- |
| `id`, `user_id`, `conversation_id` | 生成及权限范围 |
| `user_message_id`, `assistant_message_id` | 输入与输出 |
| `client_request_id` | 浏览器稳定 UUID，防止弱网重复提交 |
| `kind` | `chat` / `retry` |
| `status` | `streaming` / `completed` / `failed` / `stopped` |
| `stop_requested` | 停止端点设置，生成任务检查 |
| `error_code` | 面向应用的失败码 |
| `finished_at` | 终态时间 |

唯一约束 `(user_id, client_request_id)`。重复 UUID 返回已有 `generationId`，不保存第二条
用户消息。事务先锁定当前用户行以串行化同一用户的短创建事务；数据库部分唯一索引再保证
每个会话最多一个 streaming generation。

### `llm_configs`

单行有效配置：`provider`、`model`、`api_key_ciphertext`、`api_key_nonce`。API Key 使用
AES-256-GCM；加密主密钥不入库。读取接口只对管理员解密。

### `llm_calls`

| 字段 | 说明 |
| --- | --- |
| `conversation_id`, `generation_id` | 话题和可选生成关联 |
| `related_message_id` | 关联助手消息；标题调用可关联触发标题的首条消息 |
| `call_type` | `chat` / `title` / `retry` |
| `provider`, `model` | 实际生效配置 |
| `prompt` | JSONB，实际发送的角色、顺序和正文 |
| `response_text` | 实际完整或部分聚合返回，可为空 |
| `status` | `in_progress` / `succeeded` / `failed` / `stopped` |
| `provider_response_id` | 供应商返回 ID，可空 |
| `provider_error` | 管理员可见错误结构，可空 |
| `started_at`, `finished_at` | 调用时间 |

测试连接不写入此表。调用开始前先保存 Prompt；流式过程中分批更新 `response_text`；终态
与助手消息、generation 同一事务提交。

## 4. 事务边界

### 4.1 创建聊天

单事务：

1. 校验 `conversation_id + user_id` 或创建会话；
2. 检查 `(user_id, client_request_id)`；
3. 检查会话无 streaming 生成；
4. 创建用户消息、助手占位、generation；
5. 组装上下文并创建 in_progress `llm_calls`；
6. 提交后才启动模型流。

事务失败时不产生半条历史。模型调用失败发生在事务之后，因此保留已成功发送的用户消息
和失败助手占位，符合 PRD。

### 4.2 增量与终态

delta 按短时间窗口合并，更新助手 `content` 和调用 `response_text`，不逐 token 建事件行。
终态事务同时更新：

- generation 状态、错误和结束时间；
- assistant message 状态和最终/部分内容；
- llm_call 状态、返回、错误和结束时间；
- conversation `last_activity_at`。

### 4.3 停止与重启

停止端点只设置 `stop_requested`，幂等返回当前 generation。任务观察后写 stopped 终态。
服务启动时扫描遗留 streaming 行，写 failed/`GENERATION_INTERRUPTED`，保留部分内容。

### 4.4 标题

聊天完成事务不等待标题。进程内任务读取首条用户消息和首个成功助手消息，新增 title
调用；成功后把 `title/title_status` 更新为 final。失败不修改临时标题，也不需要 Job 表。

## 5. 分页

所有列表使用 `page`、`pageSize` 和 `total`：

- 会话和话题默认 20 条；
- 用户进入会话默认取最后一页的最近 30 条；
- 管理端消息和调用默认 50 条；
- 服务端限制 `pageSize <= 100`。

页码分页在当前无容量门槛的单机 MVP 中最易实现、测试和说明。查询始终先施加用户/管理员
权限和筛选，再计算 total 与 offset。数据规模或并发写入导致实际问题时，再以合同修订引入
keyset cursor。

## 6. 明确移除的数据结构

- `generation_events`：不提供 SSE 逐事件重放；
- `jobs`：标题失败允许保留临时标题；
- idempotency request fingerprint 表：由稳定 UUID 与唯一约束替代；
- LangGraph checkpoint/store：当前没有 Agent 工作流。

完整参考 DDL 见 `schema.sql`；可执行迁移见工程骨架 `apps/api/migrations/`。

# WI-001 需求可追溯矩阵

| PRD / Mission 要求 | 架构或数据决策 | 合同入口 |
| --- | --- | --- |
| 手机号 + `000000` 注册并自动登录 | `user-auth`，用户会话 7 天 | `POST /api/v1/user/auth/register` |
| 已注册手机号登录；未注册不静默创建 | 登录错误码区分业务状态，不创建用户 | `POST /api/v1/user/auth/login` |
| 用户和管理员登录态隔离 | 两个 API 命名空间、Cookie、会话表与中间件 | `/api/v1/user/**`、`/api/v1/admin/**` |
| 新对话发送成功后才创建会话 | 会话、用户消息、助手占位、生成任务同一事务 | `POST /api/v1/user/generations` |
| 弱网/重复点击不重复用户消息 | `Idempotency-Key` + `clientMessageId` 双重约束 | 所有生成/重试请求 |
| 流式回复 | 应用级 SSE，不透传供应商事件 | `text/event-stream` 与 `generation.*` |
| 停止保留部分内容 | cancel 请求持久化；助手、生成、调用统一终态 | `POST .../generations/{id}/stop` |
| 断线不直接失败 | 生成继续；事件序号恢复；最终以数据库为准 | `GET .../generations/{id}/stream` |
| 失败与重试不重复用户消息 | 重试创建新助手消息和新调用，复用原用户消息 | `POST .../assistant-messages/{id}/retries` |
| 多轮上下文 | 仅当前用户当前会话；保留最近完整成功轮次 | `data-model.md`、`architecture.md` |
| 首个成功回复后生成正式标题 | PostgreSQL 持久化后台任务，不阻塞聊天完成 | 会话列表/详情返回 `titleStatus` |
| 历史分组、搜索、分页 | `lastActivityAt` + Asia/Shanghai 客户端分组；标题包含搜索 | `GET /api/v1/user/conversations` |
| 首次加载最近 30 条并加载更早消息 | before 游标，默认 limit=30 | `GET .../conversations/{id}/messages` |
| 管理端 API Key 明文查看编辑 | 数据库存密文，管理员响应时服务端解密 | `GET/PUT /api/v1/admin/llm-config` |
| 测试连接使用未保存表单且不影响保存 | 测试端点接收临时 key/model，不写配置或话题调用 | `POST /api/v1/admin/llm-config/test` |
| 保存不依赖测试成功并立即生效 | 单一配置行，事务提交后新调用读取最新值 | `PUT /api/v1/admin/llm-config` |
| 管理端按话题查询 | 会话即话题，只读查询，Asia/Shanghai 日期边界 | `GET /api/v1/admin/topics` |
| 查看消息与每次实际 Prompt/返回 | `messages` 与 `llm_calls` 独立持久化 | 话题详情、messages、llm-calls |
| 测试连接不进入话题调用记录 | 测试连接不创建 `llm_calls` | 配置测试端点 |
| 普通用户不能越权 | 所有用户资源 SQL 必须带 `user_id` 条件 | 用户资源统一返回 404 防枚举 |
| 单台腾讯云部署 | Nginx + Node API + PostgreSQL + 静态站点 | `architecture.md`、骨架 README |
| 无真实凭据 | `.env.example` 只含占位符；凭据扫描 | `security.md`、验证脚本 |

## 合同覆盖清单

### 用户端

- 注册、登录、会话恢复、退出；
- 会话列表、标题搜索、游标分页；
- 会话详情与消息向前分页；
- 新会话/已有会话生成；
- 查询生成状态；
- SSE 初始流和断线恢复；
- 停止；
- 失败/停止助手消息重试。

### 管理端

- 登录、会话恢复、退出；
- 获取、保存、测试 OpenAI 配置；
- 话题筛选和分页；
- 话题概要；
- 消息列表；
- LLM 调用详情列表。

### 公共

- 健康检查；
- 统一错误结构；
- Cookie、CSRF、幂等和分页定义；
- SSE 事件、终态、心跳、停止和恢复语义。

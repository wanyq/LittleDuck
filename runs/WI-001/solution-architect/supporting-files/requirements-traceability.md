# WI-001 需求可追溯矩阵

| PRD / Mission 要求 | P0 设计决策 | 合同或验证入口 |
| --- | --- | --- |
| 手机号 + `000000` 注册并自动登录 | `user-auth` 创建用户和 7 天用户会话 | `POST /api/v1/user/auth/register` |
| 已注册手机号登录；未注册不静默创建 | 登录错误码区分状态且不创建用户 | `POST /api/v1/user/auth/login` |
| 用户和管理员登录态隔离 | 两个命名空间、Cookie、Path、会话表和认证依赖 | `/api/v1/user/**`、`/api/v1/admin/**` |
| 新对话发送成功后才创建历史 | 会话、用户消息、助手占位、generation、LLM call 同一事务 | `POST /api/v1/user/generations`、纵向测试 |
| 弱网/重复点击不重复用户消息 | 浏览器稳定 UUID + `(user_id, client_request_id)` 唯一约束 | `clientMessageId`、`clientRetryId`、409 `DUPLICATE_MESSAGE` |
| 流式回复 | 应用级 SSE，不透传供应商事件 | `streaming-protocol.md`、三个 SSE 示例 |
| 停止保留部分内容 | 持久化 `stop_requested`；消息、generation、call 同一终态 | `POST .../stop`、停止纵向测试 |
| 断线不直接失败 | 生成任务独立于响应迭代器；重进后读权威状态和部分消息 | `GET .../generations/{id}`、流协议恢复章节 |
| 进程重启结果确定 | 启动时把遗留 `streaming` 收敛为 `GENERATION_INTERRUPTED` | `GenerationRepository.fail_interrupted_generations` |
| 失败与重试不重复用户消息 | 重试复用原用户消息，新增助手消息、generation 与 call | `POST .../assistant-messages/{id}/retries` |
| 多轮上下文 | 仅当前用户/会话，最多最近 10 个已完成用户—助手轮次 | `repository.py`、`data-model.md` |
| 首个成功回复后生成正式标题 | 同进程非阻塞任务；失败保留临时标题 | `titleStatus`、`titleWillBeAttempted` |
| 历史分组、搜索和分页 | 按 `lastActivityAt`；Asia/Shanghai 分组；P0 页码分页 | `GET /api/v1/user/conversations` |
| 首次加载最近 30 条并加载更早消息 | `page/pageSize/total`，默认 30，客户端先算最后一页 | `GET .../conversations/{id}/messages` |
| 管理端 API Key 明文查看编辑 | 数据库存 AES-256-GCM 密文，管理员响应时短暂解密 | `GET/PUT /api/v1/admin/llm-config`、加密测试 |
| 测试连接使用未保存表单且不保存 | 端点接收临时值，不写配置或话题调用 | `POST /api/v1/admin/llm-config/test` |
| 保存不依赖测试成功并立即生效 | 单一配置行，提交后新调用读取最新值 | `PUT /api/v1/admin/llm-config` |
| 管理端按话题查询 | 会话即话题，只读查询，Asia/Shanghai 日期边界 | `GET /api/v1/admin/topics` |
| 查看消息及每次实际 Prompt/返回 | `messages` 与 `llm_calls` 分开持久化完整/部分值 | 话题 messages、llm-calls；纵向测试 |
| 普通用户不能越权 | 所有用户资源查询带当前 `user_id`，越权与不存在同为 404 | ownership 纵向测试 |
| 单台腾讯云部署 | Nginx + 两个静态站点 + 一个 FastAPI 进程 + PostgreSQL | `architecture.md`、骨架 README |
| 无真实凭据 | `.env.example` 仅占位；API Key 不进前端/日志；凭据扫描 | `security.md`、`pnpm security:scan` |
| 从 chatbot 演进到 Agent | 公开合同隔离 `GenerationEngine`，达到复杂度触发条件后再引入 LangGraph | `architecture.md` 的演进触发器 |

## P0 合同覆盖

用户端覆盖注册、登录、会话恢复、退出、会话列表/搜索、会话详情、消息分页、新生成、
生成状态、停止和失败/停止回复重试。管理端覆盖独立登录态、配置读取/保存/测试、话题
筛选、话题概要、消息和 LLM 调用查询。公共部分覆盖数据库 readiness、统一错误结构、
Cookie 身份域、页码分页、稳定客户端 UUID 以及 SSE 成功/失败/停止/心跳/断线语义。

## 明确延后

事件级 SSE 持久化与重放、通用请求指纹表、签名游标、独立任务表、Redis、消息队列、
独立 Agent 服务、LangGraph checkpoint/store 和多实例调度均不属于当前需求。触发条件和
迁移边界见 `architecture.md`；不得由下游单方面增加并改变已接受合同。

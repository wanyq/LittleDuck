# WI-001 revision 4：技术架构、API 合同与工程骨架

## 结论

LittleDuck MVP 采用 React + TypeScript + Vite 两个前端、Python 3.12 + FastAPI 模块化
单体后端、OpenAI 官方 Python SDK 适配层和 PostgreSQL 16。单机部署只有一个 API 进程，
当前不引入 LangGraph、LangChain、Redis、消息队列、独立 Worker 或 SSE 事件存储。

这是对当前需求的最小充分方案：当前模型路径只有一次文本生成，没有工具、条件分支、人工
审批或长任务续跑。LangGraph 的 durable execution、checkpoint 和 human-in-the-loop 能力在
此时没有业务对象承载，反而会形成业务状态与图状态两套事实源。公开业务层保留
`GenerationEngine` 接口；未来出现多步工具链、条件路由、人工审批、可恢复长任务或多 Agent
时，再在接口内部接入 `LangGraphGenerationEngine`。

## 系统和模块边界

- Nginx 提供用户 H5、`/admin/` 静态站点，并反向代理 `/api`、`/healthz`；
- FastAPI 负责认证依赖、同源检查、HTTP/SSE 适配和进程内生成任务；
- repository 负责带所有者条件的事务与查询，路由不直接操作 ORM；
- `GenerationEngine` 隔离模型 SDK，前端不接触 API Key 或供应商事件；
- PostgreSQL 是会话、消息、generation、配置和实际 LLM 调用的唯一权威存储；
- Alembic 是可执行结构变更入口，`schema.sql` 只是便于评审的参考 DDL。

候选方案和取舍见 `supporting-files/architecture.md`。其中比较了 TypeScript/Fastify、
Python/FastAPI + SDK、Python/FastAPI + LangGraph 三条可行路线，并逐项区分 P0 与延后机制。

## 后端对前端的接口

机器合同为 OpenAPI 3.0.3，共 21 个 path、22 个 operation：

| 范围 | 数量 | 用途 |
| --- | ---: | --- |
| 公共 | 1 | API 与 PostgreSQL readiness |
| 用户认证 | 4 | 注册、登录、恢复会话、退出 |
| 用户会话/消息 | 3 | 会话列表/搜索、会话详情、消息分页 |
| 用户生成 | 4 | 新消息 SSE、权威生成状态、停止、重试 |
| 管理认证 | 3 | 独立管理员登录、恢复会话、退出 |
| 管理配置 | 3 | 读取、保存、测试未保存的 OpenAI 配置 |
| 管理话题 | 4 | 话题列表、概要、消息、实际 LLM 调用 |

完整路径、字段、状态码和 Schema 见 `supporting-files/contracts/openapi.yaml`；错误码见
`supporting-files/contracts/error-catalog.md`；可复制的请求响应见
`supporting-files/examples/http-examples.md`。前端 TypeScript 类型由该 OpenAPI 自动生成到
`supporting-files/skeleton/packages/contracts/src/generated.ts`。

## 数据、认证和越权防护

- 用户与管理员使用不同 API 前缀、Cookie 名、Cookie Path、Session 表和认证依赖；
- Session Token 至少 256 位，数据库只保存 SHA-256 哈希，默认 7 天；
- 所有用户资源查询同时包含当前 `user_id`，不存在与越权统一 404；
- 同源部署不另发 CSRF Token；SameSite=Lax Cookie、精确 Origin、Fetch Metadata、JSON-only
  mutation 和无宽松 CORS 共同防护跨站写入；
- 浏览器为每次发送生成稳定 UUID，数据库唯一约束防止重复消息；重复返回已有
  `generationId`，不引入通用请求指纹表；
- OpenAI API Key 以 AES-256-GCM 密文 + 随机 nonce 保存，主密钥只来自部署 Secret；只对
  已认证管理员短暂解密并完整显示，响应不缓存、日志不记录；
- `llm_calls` 保存实际 Prompt、完整/部分返回、终态和筛选后的供应商错误，测试连接不进入
  用户话题调用记录。

表、约束、事务与页码分页见 `supporting-files/data-model.md`、
`supporting-files/schema.sql`；安全边界见 `supporting-files/security.md`。

## SSE 与中断语义

生成使用 `fetch()` POST 建立 SSE，顺序为 `generation.started`、零到多个
`generation.delta`、恰好一个 `generation.completed|failed|stopped`；可选 heartbeat 不推进
业务 sequence。模型失败发生在流建立后时通过 `generation.failed` 表达，HTTP 仍为 200。

停止请求先持久化 `stopRequested=true`，任务在下一个取消点停止供应商流，保留部分正文，
并把 generation、助手消息和 LLM call 写为同一 stopped 终态。浏览器断线只移除订阅者，
不取消进程内任务；重新进入后读取 generation 与消息，仍为 streaming 时短轮询。P0 不做
事件级重放。进程重启后，启动逻辑把遗留 streaming 收敛为 failed/
`GENERATION_INTERRUPTED`，保留部分内容并允许重试。

协议和三个完整流示例见 `supporting-files/contracts/streaming-protocol.md` 与
`supporting-files/examples/sse-chat-*.txt`。

## 可运行工程骨架

`supporting-files/skeleton/` 包含：

- 两个 React/TypeScript/Vite 独立构建入口；
- FastAPI、Pydantic、SQLAlchemy async、psycopg 和 Alembic migration；
- 确定性、无凭据的 `DemoGenerationEngine`；
- 请求 → PostgreSQL 事务 → SSE → 完成终态 → 权威读取纵向切片；
- 停止并保留部分内容、重复 UUID、越权 404、同源拒绝、Prompt/响应记录和 AES-GCM 测试；
- OpenAPI lint/类型生成、SSE 示例校验、无第三方运行依赖的合同 Mock 和凭据扫描；
- 只有占位值的 `.env.example`。

骨架只证明关键边界，不实现完整注册、管理查询、真实 OpenAI provider 或产品 UI。安装、
迁移、启动和验证命令见 `supporting-files/skeleton/README.md`。

## 验证结论

详细环境、命令、实际输出和边界见 `supporting-files/validation-report.md`。本次退修已实际
完成：

- PostgreSQL migration `upgrade -> downgrade -> upgrade`；
- Python ruff 与严格 mypy；
- PostgreSQL 纵向测试 5/5；
- OpenAPI lint 与 TypeScript 类型再生成；
- 三类 SSE 示例的字段、顺序与唯一终态校验；
- 两个前端和两个共享包的 TypeScript typecheck 与生产构建；
- 真实 FastAPI 进程数据库 readiness；
- 合同 Mock JSON、成功/失败/停止/重复场景；
- 整个交付目录高置信凭据扫描。

## 交付索引

- 架构：`supporting-files/architecture.md`
- 需求追溯：`supporting-files/requirements-traceability.md`
- 数据模型和 DDL：`supporting-files/data-model.md`、`supporting-files/schema.sql`
- 安全：`supporting-files/security.md`
- OpenAPI / SSE / 错误：`supporting-files/contracts/`
- HTTP / SSE 示例：`supporting-files/examples/`
- 可运行骨架、migration、测试、Mock、生成类型：`supporting-files/skeleton/`
- 外部技术来源：`supporting-files/sources.md`
- 验证证据：`supporting-files/validation-report.md`

## 接受后的约束

后端、用户端、管理端和集成工作只能消费 Coordinator 接受后的 artifact。合同接受后，任何
路径、字段、状态码、Cookie、分页、重复提交或 SSE 语义变化都必须由 Coordinator 创建合同
修订 Work Item；下游不得单方面修改。内部替换 OpenAI SDK 或未来增加 LangGraph 只有在不
改变公开语义时才属于实现细节。

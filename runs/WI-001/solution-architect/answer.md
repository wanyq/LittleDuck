# WI-001 技术架构、API 合同与工程骨架

## 结论

LittleDuck MVP 的初始技术基线已完成：

- 采用适合单台腾讯云服务器的 TypeScript 模块化单体架构；
- 用户 H5、PC 管理端是两个独立 React/Vite 构建入口；
- Fastify API 通过 `/api/v1/user` 与 `/api/v1/admin` 隔离身份域；
- PostgreSQL 作为用户、会话、消息、生成、LLM 调用、流事件、配置和后台任务的权威存储；
- OpenAI 只在服务端 provider adapter 中使用，前端不接触 API Key 或供应商事件；
- 初始合同由 OpenAPI 3.0、应用级 SSE 协议、错误目录、示例和可运行 Mock 共同组成；
- 工程骨架可在无生产凭据的本地环境完成安装、类型检查、测试、构建和最小启动；
- 未实现完整产品业务，保持在 WI-001 范围内。

## 关键架构决策

1. 单机部署使用 Nginx + 两个静态站点 + 一个 Node.js API + PostgreSQL。
2. 普通用户与管理员使用不同 API 前缀、Cookie、Cookie Path、Session 表和认证中间件。
3. Session Token 只存哈希；写请求使用 CSRF Token；用户资源查询必须把当前 `user_id` 纳入 SQL。
4. OpenAI API Key 为满足管理端明文查看而使用 AES-256-GCM 可逆加密，主密钥只从 Secret/环境变量注入。
5. 首条消息通过事务同时创建会话、用户消息、助手占位、生成任务和 LLM 调用；前置失败不创建历史会话。
6. 重试复用原用户消息并新增助手消息与调用记录；失败/停止助手内容不进入成功上下文。
7. LittleDuck SSE 使用持久化递增序号，支持完成、失败、停止和至少 24 小时的事件重放；浏览器断线不等于停止。
8. 标题生成通过 PostgreSQL 持久化后台任务异步执行，不阻塞聊天完成。

## API 合同快照

- OpenAPI：3.0.3；
- 路径：22；
- 身份域：`UserCookie`、`AdminCookie`；
- 用户端：注册、登录、Session、退出、会话、消息、生成、状态、恢复、停止、重试；
- 管理端：登录、Session、退出、LLM 配置读取/保存/测试、话题/消息/LLM 调用查询；
- 流事件：`generation.started`、`generation.delta`、`generation.completed`、`generation.failed`、`generation.stopped`、`heartbeat`；
- 创建和重试要求 `Idempotency-Key`；
- 分页使用不透明签名 cursor；
- 普通用户越权和不存在统一为 404 `RESOURCE_NOT_FOUND`。

## 交付索引

### 架构、数据与安全

- `supporting-files/architecture.md`：系统上下文、部署、模块边界、业务流程、状态机、故障恢复和版本规则；
- `supporting-files/requirements-traceability.md`：PRD/Mission 到架构和端点的可追溯矩阵；
- `supporting-files/data-model.md`：实体、事务、权限查询和分页设计；
- `supporting-files/schema.sql`：PostgreSQL 16+ 参考 DDL、约束和索引；
- `supporting-files/security.md`：认证、CSRF、越权防护、管理员密码、API Key 加密和日志规则；
- `supporting-files/sources.md`：OpenAI 官方技术来源及本方案推导边界。

### 合同与示例

- `supporting-files/contracts/openapi.yaml`：机器可读 OpenAPI 3.0 合同；
- `supporting-files/contracts/streaming-protocol.md`：SSE 帧、事件载荷、顺序、终态、停止和恢复语义；
- `supporting-files/contracts/error-catalog.md`：HTTP 和流内错误码；
- `supporting-files/examples/http-examples.md`：认证、生成、恢复、停止、重试、配置和话题调用示例；
- `supporting-files/examples/sse-chat-success.txt`：成功流；
- `supporting-files/examples/sse-chat-failure.txt`：失败流；
- `supporting-files/examples/sse-chat-stopped.txt`：停止流。

### 工程骨架与 Mock

- `supporting-files/skeleton/README.md`：安装、验证、启动和下游责任；
- `supporting-files/skeleton/.env.example`：无真实凭据的环境变量占位；
- `supporting-files/skeleton/pnpm-lock.yaml`：可复现依赖锁；
- `supporting-files/skeleton/apps/api/`：Fastify 健康检查、配置入口、模块目录约束和测试；
- `supporting-files/skeleton/apps/user-web/`：用户 H5 独立构建入口；
- `supporting-files/skeleton/apps/admin-web/`：PC 管理端 `/admin/` 独立构建入口；
- `supporting-files/skeleton/packages/contracts/`：由 OpenAPI 生成的 TypeScript 类型；
- `supporting-files/skeleton/scripts/mock-server.mjs`：JSON + SSE 合同 Mock；
- `supporting-files/skeleton/scripts/check-sse-examples.mjs`：SSE 顺序和终态检查；
- `supporting-files/skeleton/scripts/scan-secrets.mjs`：高置信凭据扫描。

## 验证结论

详细记录见 `supporting-files/validation-report.md`。

- OpenAPI lint：通过；
- OpenAPI TypeScript 类型生成：通过；
- SSE 三类示例顺序、JSON 和唯一终态检查：通过；
- 全 workspace TypeScript typecheck：通过；
- API 健康检查测试：1/1 通过；
- API、用户 H5、PC 管理端生产构建：通过；
- API 实际进程启动与 `/healthz`：通过；
- Mock 会话 JSON 与成功 SSE `started -> delta -> completed`：通过；
- 高置信凭据模式扫描：通过；
- Git whitespace 检查将在提交前执行。

`schema.sql` 是 WI-003 的参考 DDL，不是本 Run 中执行的生产 migration；WI-003 仍需在真实 PostgreSQL 上形成和验证正式 migration。

## 下游约束

- 后端、用户端、管理端和集成工作只能消费 Coordinator 接受后的 Artifact。
- 后端实现不得改变路径、字段、必填性、状态码、错误码、Cookie、CSRF、分页、幂等和 SSE 事件语义。
- 前端可立即基于已接受 OpenAPI 类型、HTTP/SSE 示例和 Mock 独立开发。
- 合同接受后的任何语义变更必须向 Coordinator 发送 `work_item_proposed`，由独立合同修订 Work Item 交付完整合并合同。
- OpenAI 供应商适配层内部变化若不改变 LittleDuck 合同，可由后端实现内部处理。

## 明确未实现

- 完整注册、聊天、管理端业务；
- 真实数据库 migration 与业务 repository；
- 真实 OpenAI 调用；
- 完整 UI 视觉与交互；
- 腾讯云生产部署。

这些分别属于后续 Work Items。

# LittleDuck MVP 工程骨架

本目录是可启动的架构纵向切片，不是完整产品。它证明 React/TypeScript 两个前端入口、
Python/FastAPI API、PostgreSQL migration、请求持久化、SSE 输出、终态读取、合同 Mock
和合同校验可以协同工作；真实 OpenAI 调用、完整认证和完整页面属于后续 Work Item。

## 技术环境

- Python 3.12、uv 0.11+
- PostgreSQL 16+
- Node.js 24、pnpm 11.10

## 安装

```bash
pnpm install --frozen-lockfile
uv sync --directory apps/api --frozen
cp .env.example apps/api/.env
```

`.env.example` 只有本地占位值。不要提交复制后的 `.env`，也不要把真实 API Key、
数据库密码或加密主密钥写入本目录。

## PostgreSQL 与 migration

先创建仅供本地开发的 `littleduck` 数据库和角色，并把占位数据库密码改成本地值，
然后执行：

```bash
pnpm api:migrate
pnpm api:bootstrap-admin
```

正式数据库结构由 `apps/api/migrations/` 管理；相邻的 `../schema.sql` 是便于评审的等价
参考 DDL。骨架已验证 `upgrade -> downgrade -> upgrade`。管理员 bootstrap 是 migration
之后的独立、可重复部署步骤：首次以 scrypt 强哈希创建 PRD 指定的 `admin/admin`；重复执行
只返回 already exists，不创建重复行，也不覆盖人工修改后的哈希或输出密码/哈希。后续部署
Work Item 必须在每次 migration 后调用该命令。

## 启动真实纵向切片

```bash
pnpm start:api
curl http://127.0.0.1:3000/healthz
```

数据库可用且启动遗留 streaming 已收敛时预期 `status=ok`、`database=ok`。数据库不可用时
应用仍启动并返回 HTTP 503 `status=degraded`；后台恢复器重试连接，恢复后仅处理启动 cutoff
前的遗留 generation，完成后 readiness 才变为 200。测试中的确定性
`DemoGenerationEngine` 不需要任何供应商凭据。

当前实现端点只覆盖最小证明切片：

- `GET /healthz`
- `POST /api/v1/user/generations`
- `GET /api/v1/user/generations/{generationId}`
- `POST /api/v1/user/generations/{generationId}/stop`
- `POST /api/v1/user/assistant-messages/{assistantMessageId}/retries`
- `POST /api/v1/user/auth/logout`

完整产品端点以 `../contracts/openapi.yaml` 为准，由下游后端 Work Item 实现。

## 验证

```bash
pnpm contract:lint
pnpm contract:types
pnpm examples:check
pnpm security:scan
pnpm api:lint
pnpm typecheck
pnpm test
pnpm build
```

`pnpm test` 需要本地 PostgreSQL 测试库，可用 `TEST_DATABASE_URL` 覆盖默认测试 URL。
纵向测试覆盖事务持久化、SSE `started -> delta -> completed`、权威终态、重复/越权、trim
后空消息零写入、空 delta、精确 Session logout、重试稳定序号、用户/管理员跨页顺序、12 轮
token 预算、管理员强哈希幂等 bootstrap、数据库 degraded 启动/cutoff 恢复、上海数据库时区
下 UTC 输出，以及真实 JSON/SSE 对封闭 OpenAPI Schema 的校验。

## 合同 Mock

```bash
pnpm mock
pnpm dev:user
pnpm dev:admin
```

- Mock 监听 `127.0.0.1:4010`，两个 Vite 入口把 `/api` 和 `/healthz` 代理到它。
- `X-Mock-Scenario` 可选 `chat-success`、`chat-failure`、`chat-stopped`、`chat-slow`
  或 `config-test-failure`。
- Mock 不实现会话鉴权，只用于前端合同开发；安全行为必须用真实 API 测试。

## 目录责任

- `apps/api`：FastAPI 模块化单体、SQLAlchemy、Alembic 和纵向测试；
- `apps/user-web`：React/TypeScript 用户 H5 构建入口；
- `apps/admin-web`：React/TypeScript PC 管理端构建入口；
- `packages/contracts`：从 OpenAPI 生成的 TypeScript 类型；
- `packages/shared`：不含权限规则的前端共享值对象；
- `scripts/mock-server.mjs`：无第三方运行时依赖的 JSON + SSE 合同 Mock；
- `scripts/check-sse-examples.mjs`：事件顺序、JSON 和唯一终态检查；
- `scripts/scan-secrets.mjs`：交付材料高置信凭据扫描。

## 下游约束

- WI-003 使用 `GenerationEngine` 接口接入 OpenAI Python SDK，不改变公开合同；
- provider adapter 必须同时实现当前模型的 token counter，并把合同配置的输出预留真实传给
  OpenAI；不得恢复固定轮数裁剪；
- 当前不引入 LangGraph、Redis、任务队列、SSE 事件存储或独立 Agent 服务；
- WI-004/WI-005 只依赖 Coordinator 接受后的 OpenAPI、示例、类型和 Mock；
- 合同接受后，路径、字段、状态码、认证、分页、幂等或 SSE 语义变化必须新建合同修订
  Work Item。

# LittleDuck MVP 工程骨架

本目录只证明工程边界、合同工具、健康检查、前端构建和 Mock 可以运行，不包含完整产品实现。

## 环境

- Node.js 24
- pnpm 11.10.0

## 安装和验证

```bash
pnpm install --frozen-lockfile
pnpm contract:lint
pnpm examples:check
pnpm security:scan
pnpm typecheck
pnpm test
pnpm build
```

## 最小启动

API 健康检查不需要生产凭据：

```bash
cp .env.example .env
pnpm dev:api
curl http://127.0.0.1:3000/healthz
```

预期：

```json
{"status":"ok","database":"not_checked","time":"..."}
```

`database=not_checked` 只用于 WI-001 骨架。WI-003 接入数据库后必须改为真实 readiness 检查。

## Mock

```bash
pnpm mock
pnpm dev:user
pnpm dev:admin
```

- Mock 默认监听 `127.0.0.1:4010`。
- 两个 Vite 项目把 `/api` 和 `/healthz` 代理到 Mock。
- 生成端点可用 `X-Mock-Scenario` 选择 `chat-success`、`chat-failure`、`chat-stopped` 或 `chat-slow`。
- 前端合同类型由相邻 `../contracts/openapi.yaml` 生成。

## 目录责任

- `apps/api`：Fastify 模块化单体入口和健康检查；
- `apps/user-web`：H5 独立构建入口；
- `apps/admin-web`：PC 管理端独立构建入口；
- `packages/contracts`：由 OpenAPI 生成的 TypeScript 类型；
- `packages/shared`：不含业务权限的共享值对象；
- `scripts/mock-server.mjs`：依赖 Node 标准库的合同 Mock。
- `scripts/check-sse-examples.mjs`：检查示例事件顺序、JSON 和唯一终态；
- `scripts/scan-secrets.mjs`：对交付材料执行高置信凭据模式扫描。

## 后续 Work Item 约束

- WI-003 在 `apps/api/src/modules` 中实现服务端，不改变合同语义；
- WI-004 和 WI-005 只依赖已接受 OpenAPI、SSE 和 Mock；
- WI-006 校验真实实现、两个客户端与当前合同一致；
- 任何路径、字段、状态码、错误码、认证、分页、幂等或事件语义变化必须走合同修订 Work Item。

# WI-001 验证报告

验证时间：2026-07-17T01:55:11Z

## 环境

- Node.js `v24.14.0`
- pnpm `11.10.0`
- 工程目录：`supporting-files/skeleton`
- 未使用生产 API Key、服务器凭据或生产环境变量

## 自动检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 可复现安装 | `pnpm install --frozen-lockfile` | 通过，6 个 workspace project，锁文件无变化 |
| OpenAPI lint | `pnpm contract:lint` | 通过，Redocly 报告 API description valid |
| 类型生成 | `pnpm contract:types` | 通过，生成 `packages/contracts/src/generated.ts` |
| SSE 示例 | `pnpm examples:check` | 通过，成功 4 个持久事件、失败 3 个、停止 3 个 |
| 凭据扫描 | `pnpm security:scan` | 通过，无高置信凭据模式 |
| TypeScript | `pnpm typecheck` | 通过，API、两个前端、contracts、shared 全部通过 |
| API 测试 | `pnpm test` | 通过，1 test / 1 pass |
| 生产构建 | `pnpm build` | 通过，API、用户 H5、PC 管理端、contracts、shared 均构建成功 |

## 实际启动检查

### API

执行：

```bash
pnpm start:api
curl --fail --silent http://127.0.0.1:3000/healthz
```

实际响应：

```json
{
  "status": "ok",
  "database": "not_checked",
  "time": "2026-07-16T12:53:19.322Z"
}
```

`not_checked` 是 WI-001 骨架专用值。WI-003 接入数据库后必须实现真实 readiness。

### 合同 Mock

执行：

```bash
pnpm mock
curl http://127.0.0.1:4010/api/v1/user/conversations
```

结果：返回符合合同字段的会话页。

向 `/api/v1/user/generations` 发送 `X-Mock-Scenario: chat-success` 后实际收到：

```text
generation.started
generation.delta
generation.delta
generation.completed
```

事件 `id` 和 JSON `sequence` 均为 1、2、3、4，终态唯一。

## 合同覆盖检查

- OpenAPI 3.0.3，共 22 条 path；
- 用户和管理员 Cookie Security Scheme 分离；
- mutation 定义 CSRF；
- 生成和重试定义幂等键；
- 会话、消息、话题和调用定义分页；
- SSE 定义成功、失败、停止、心跳和恢复；
- 管理配置定义读取、保存和使用未保存值测试；
- 管理话题定义实际 Prompt/返回查询；
- 错误目录覆盖认证、权限、越权、冲突、限流、流重放过期和 LLM 不可用。

## 安全检查

扫描范围是整个 `supporting-files/`，排除安装依赖、构建产物和依赖锁中的第三方哈希。检查模式包括：

- 私钥 PEM/OpenSSH 头；
- OpenAI 风格 Key；
- GitHub Token；
- AWS Access Key；
- 非占位加密主密钥；
- 非占位数据库密码。

此外人工确认：

- SSH 私钥及其本地路径未写入 Run；
- `.env.example` 仅含 `REPLACE_*` 占位；
- Mock Cookie、CSRF 和 API Key 均明确为 mock/placeholder；
- OpenAI API Key 只在安全设计中以字段名或占位符出现。

## 边界

`schema.sql` 是架构参考 DDL，本环境没有 PostgreSQL 客户端或实例，因此本 Run 未把它作为生产 migration 执行。WI-003 必须生成正式 migration，并在 PostgreSQL 16+ 上验证创建、约束、事务和回滚。

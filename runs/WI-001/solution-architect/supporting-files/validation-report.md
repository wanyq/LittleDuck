# WI-001 revision 4 验证报告

验证时间：2026-07-17T03:47:34Z 至 2026-07-17T03:49:00Z。

## 环境

- macOS arm64 本地隔离副本
- Node.js `v24.14.0`
- pnpm `11.10.0`
- Python `3.12.13`
- uv `0.11.29`
- PostgreSQL `16.14`
- 未使用真实 OpenAI Key、服务器凭据、生产数据库或生产环境变量

## 自动验证结果

| 检查 | 实际命令 | 结果 |
| --- | --- | --- |
| Node 依赖锁 | `CI=true pnpm install --frozen-lockfile` | 通过；5 个 workspace project，锁文件无变化 |
| Python 依赖锁 | `uv sync --directory apps/api --frozen` | 通过；按 `uv.lock` 检查 46 个包 |
| OpenAPI lint | `pnpm contract:lint` | 通过；OpenAPI 3.0.3 描述 valid |
| TypeScript 合同生成 | `pnpm contract:types` | 通过；重新生成 `packages/contracts/src/generated.ts` |
| OpenAPI 结构检查 | Python/YAML 断言 | 21 paths、22 operations、22 个唯一 operationId；无流重放 path |
| 旧合同残留扫描 | `rg` 检查合同、示例、Mock、生成类型 | 通过；无旧 CSRF header、通用幂等 header、游标或重放字段 |
| SSE 示例 | `pnpm examples:check` | 通过；成功 4、失败 3、停止 3 个有序业务事件，均恰好一个终态 |
| 凭据扫描 | `pnpm security:scan` | 通过；未发现高置信私钥、Token 或生产凭据模式 |
| Python lint | `uv run --directory apps/api ruff check .` | 通过 |
| Python strict typing | `uv run --directory apps/api mypy src` | 通过；10 个 source files 无问题 |
| PostgreSQL migration | `alembic downgrade base` 后 `alembic upgrade head` | 通过；事务 DDL 完成回退与再升级 |
| API 测试 | `uv run --directory apps/api pytest` | 通过；5/5，耗时 0.51 秒 |
| 前端/共享类型 | `pnpm -r typecheck` | 通过；两个前端、contracts、shared |
| 前端/共享构建 | `pnpm -r build` | 通过；两个 Vite 生产构建及两个 TS package |
| Git whitespace | `git diff --check` | 通过（修正 `.env.example` EOF 后复查） |

## 纵向切片测试证据

测试连接本机 `littleduck_test` PostgreSQL，执行真实 SQLAlchemy 事务，不使用内存数据库。
5 项测试覆盖：

1. OpenAPI 基线包含骨架实际实现的 health、创建生成、状态读取和停止 operation；
2. 随机运行时主密钥的 AES-256-GCM 加密、密文不含明文、解密得到完整 Key；
3. 非 32 字节主密钥被拒绝；
4. HTTP 请求 → PostgreSQL 创建会话/用户消息/助手占位/generation/LLM call → 三段 SSE
   delta → completed → GET 权威终态；同时验证同源拒绝、重复 UUID 409、用户 B 越权 404、
   实际 Prompt 和聚合响应入库；
5. 可控生成引擎先写部分内容，停止请求持久化 `stopRequested`，随后仅发送 stopped 终态，
   消息和 LLM call 均保留相同部分内容并收敛到 stopped。

数据库 migration 还包含 `(user_id, client_request_id)` 唯一约束、每会话最多一个 streaming
generation 的部分唯一索引、单行 LLM 配置约束和每 generation 一个 LLM call 约束。

## 实际启动

### FastAPI

以测试数据库 URL 启动真实 Uvicorn 进程后请求 `GET /healthz`，实际得到 HTTP 200：

```json
{"status":"ok","database":"ok","time":"2026-07-17T03:48:31.864351+00:00"}
```

随后正常触发 lifespan shutdown。readiness 确实执行 `SELECT 1`，不再返回骨架占位状态。

### 合同 Mock

启动 `pnpm mock` 后实际验证：

- 会话页返回 `items/page/pageSize/total`；
- 成功：`started -> delta -> delta -> completed`；
- 失败：`started -> delta -> failed`；
- 停止：`started -> delta -> stopped`；
- 重复提交：HTTP 409 `DUPLICATE_MESSAGE` 并附已有 `generationId`。

## 安全检查

- Session 测试数据只使用本地演示字符串，数据库只存 SHA-256；
- 用户 A 的 generation 由用户 B 请求时返回 404；
- 不可信 Origin 在任何写入前返回 403；
- API Key 加密测试主密钥由 `os.urandom(32)` 在测试进程内生成，不落盘；
- `.env.example` 只包含 `REPLACE_*` 占位，不包含可用 Key 或密码；
- SSH 私钥、SSH 私钥路径和 Git 连接设置均未进入 Run 文件；
- Mock Cookie、API Key 和模型名均明确为 mock/example 值。

## 未验证边界与下游责任

- 骨架只实现 22 个合同 operation 中的 4 个关键 operation；完整认证、列表、管理配置与
  管理话题查询由后端 Work Item 实现并接受合同测试；
- `DemoGenerationEngine` 是确定性无凭据实现，未调用真实 OpenAI；provider adapter、供应商
  错误映射和真实流取消由后端 Work Item 验证；
- 页面断线后的任务独立性由实现结构保证，恢复语义由状态读取合同定义；本 Run 未做浏览器
  强制断网和 API 进程崩溃的黑盒故障注入；
- 当前部署假设一个 Uvicorn worker。增加多 worker 或多实例前必须引入共享执行协调机制并
  创建架构/合同修订 Work Item；
- 未执行容量、长时间 soak、渗透测试或腾讯云生产部署，这些不在 WI-001 架构基线范围。

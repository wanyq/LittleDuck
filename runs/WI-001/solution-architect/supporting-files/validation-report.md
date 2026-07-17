# WI-001 revision 7 验证报告

验证时间：2026-07-17T08:21:56Z 至 2026-07-17T09:29:37Z。

## 环境

- macOS arm64 独立仓库副本
- Node.js `v24.14.0`、pnpm `11.10.0`
- Python `3.12.13`
- PostgreSQL `16.14`
- 未使用真实 OpenAI Key、服务器凭据、生产数据库或生产环境变量

## 自动验证结果

| 检查 | 实际命令 | 结果 |
| --- | --- | --- |
| Node 依赖锁 | `CI=true pnpm install --frozen-lockfile` | 通过；5 个 workspace，Already up to date |
| OpenAPI lint | `CI=true pnpm contract:lint` | 通过；OpenAPI 3.0.3 valid |
| TypeScript 合同生成 | `CI=true pnpm contract:types` | 通过；由 revision 7 OpenAPI 再生成 |
| SSE 示例 | `CI=true pnpm examples:check` | 通过；成功 4、失败 3、停止 3 个业务事件 |
| 凭据扫描 | `CI=true pnpm security:scan` | 通过；无高置信凭据模式 |
| Python lint | `apps/api/.venv/bin/ruff check apps/api/src apps/api/tests` | 通过 |
| Python strict typing | `apps/api/.venv/bin/mypy apps/api/src` | 通过；14 个 source files |
| PostgreSQL migration | `alembic downgrade base && alembic upgrade head` | 通过；真实事务 DDL |
| ORM/migration 漂移 | `alembic check` | 通过；No new upgrade operations detected |
| 管理员 bootstrap | 连续两次 `python -m littleduck_api.bootstrap_admin` | 依次输出 created / already exists，不输出凭据 |
| API / 数据 / 合同测试 | `apps/api/.venv/bin/pytest apps/api/tests -q` | 通过；17/17 |
| 前端/共享类型 | `CI=true pnpm -r typecheck` | 通过；两个前端与两个 package |
| 前端/共享构建 | `CI=true pnpm -r build` | 通过；两个 Vite production build |
| 真实 API 进程 | Uvicorn + `curl /healthz` | 通过；HTTP 200、UTC `Z` 时间 |
| 合同 Mock 黑盒 | Node Mock + curl | 通过；health、空白 400、成功 SSE |

`uv.lock` 和 Python 依赖声明未增加新包；管理员强哈希复用已锁定的 `cryptography` scrypt。

## 第二次审核整改证据

### 1. 管理员初始化

- `python -m littleduck_api.bootstrap_admin` 是 migration 后的明确入口；package script 为
  `pnpm api:bootstrap-admin`。
- 首次以随机 salt、memory-hard scrypt 强哈希创建 Mission 指定 `admin/admin`。
- PostgreSQL `ON CONFLICT DO NOTHING` 保证重复执行不增加第二行、不改 ID、不覆盖原哈希。
- 测试验证明文不落库、正确/错误密码验证和二次执行不变。

### 2. 精确 user Session

- 认证返回 `UserPrincipal(user_id, session_id)`；创建事务锁定并重新校验精确 Session。
- `generations.initiating_session_id` 非空关联 `user_sessions`，历史不级联删除。
- 双 Session 测试同时生成：logout A 只撤销 A，只产生 A 的 `stoppedBy=logout`；B Session 和
  generation 正常完成。显式 `/stop` 仍按合同以当前用户授权。

### 3. token-aware 上下文

- 删除固定 `.limit(10)`；`GenerationEngine` 同时提供当前模型 token counter。
- 输入预算为模型 context window 减实际 output 上限与固定 Prompt 预留；超限从最早完整
  用户—成功助手轮次删除。
- 测试证明 12 个小轮次可全部保留，预算缩小时只删除完整轮次；实际 Prompt、估算输入 token
  和输出上限写入 `llm_calls`。
- 当前输入自身超过预算时事务整体回滚，conversation/message/generation/llm_call 均为零。

### 4. 稳定消息顺序

- `conversations.next_message_sequence` 在行锁内分配；唯一约束为
  `(conversation_id, sequence)`。
- 普通发送预留两个序号；重试复用原用户消息，只新增一个助手序号。
- 测试把所有 `created_at` 强制设为相同值，仍验证上下文和用户/管理员 2 条分页顺序均为
  `1,2,3,4,5`，无重复、遗漏或反序。

### 5. trim、空 delta 与零副作用

- Pydantic 在长度约束前 trim；repository 在事务前防御性复核 1..4000。
- 纯空白 HTTP 请求返回 400 `VALIDATION_ERROR`；conversation、message、generation、llm_call
  计数均为零。
- 引擎 `"", "a", "", "b"` 只产生两个非空 delta，sequence 连续，最终正文为 `ab`。

### 6. 封闭合同

- OpenAPI `Generation` 声明并要求 nullable `errorCode/finishedAt`；`Message` 声明稳定
  `sequence`；`HealthResponse` 也使用 `additionalProperties:false`。
- 真实 health、GET GenerationResponse、400 ErrorEnvelope 与每一种实际 SSE data 均由测试
  递归校验 required、additionalProperties、类型、枚举、长度、UUID 和 UTC date-time。
- Mock、三类 SSE 示例与自动生成 TypeScript 类型同步包含新字段。

### 7. UTC

- DB 时间全部经单一 UTC serializer 输出 `Z`；事件和 health 使用同一边界。
- 测试在 PostgreSQL Session 中执行 `SET TIME ZONE 'Asia/Shanghai'`，generation/message 的
  started/created/updated/finished 仍全部输出 UTC `Z`。

### 8. degraded 启动与恢复

- 无效数据库地址下 lifespan 快速成功，`/healthz` 实际返回 503 degraded。
- 恢复器记录 UTC startup cutoff、重试连接，并只收敛 cutoff 前仍为 streaming 的记录；行锁
  和终态复核使重复执行幂等。
- 测试证明旧 generation 变为 failed/`GENERATION_INTERRUPTED`，cutoff 后 generation 保持
  streaming，第二次恢复处理数为零。

## 实际进程与 Mock 结果

真实 Uvicorn 进程连接测试数据库后：

```json
{"status":"ok","database":"ok","time":"2026-07-17T09:10:33.254041Z"}
```

合同 Mock 的空白正文请求返回 HTTP 400 `VALIDATION_ERROR`；成功请求返回
`started -> delta -> delta -> completed`，终态 generation 含 `errorCode:null`、UTC 时间，
assistantMessage 含稳定 `sequence:2`。

## 未验证边界与下游责任

- 骨架实现 22 个合同 operation 中的 6 个关键 operation；完整注册/登录、列表、管理配置和
  管理话题查询由后端 Work Item 实现并接受同一合同测试。
- `DemoGenerationEngine` 无真实凭据；OpenAI adapter 必须提供当前模型准确 token counter，
  并把记录的 `max_output_tokens` 真实传给供应商。
- degraded 恢复按 Mission 的单 Uvicorn worker 假设设计；多 worker/多实例需要共享执行租约或
  Worker，并应先创建架构/合同修订 Work Item。
- 未执行容量、长时间 soak、渗透测试或腾讯云生产部署；这些不属于 WI-001 架构基线。

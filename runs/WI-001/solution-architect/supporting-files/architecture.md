# LittleDuck MVP 最小充分技术架构

## 1. 决策结论

LittleDuck MVP 采用：

- 用户 H5、PC 管理端：React + TypeScript + Vite；
- 服务端：Python 3.12 + FastAPI + Pydantic；
- 模型调用：OpenAI 官方 Python SDK，经 `GenerationEngine` 端口隔离；
- 持久化：PostgreSQL 16、SQLAlchemy 2、Alembic、psycopg；
- 流式传输：应用级 SSE；
- 部署：Nginx + 两个静态站点 + 单个 FastAPI 进程 + PostgreSQL。

本期不引入 LangGraph、LangChain、Redis、消息队列、独立 Agent 服务、持久化 SSE
事件日志或后台任务表。它们都不能直接增加当前 P0 功能，却会增加状态一致性、部署、
故障恢复和合同复杂度。

## 2. 决策依据

当前 Mission 的模型能力仅为纯文本多轮聊天、标题生成和失败/停止后的重试；明确排除
联网搜索、RAG、插件、工具调用和复杂 Agent。系统没有容量或性能验收指标，目标部署为
单台腾讯云服务器。因此技术基线应优先满足：

1. 前后端可依据固定 HTTP/SSE 合同并行开发；
2. 会话、消息和实际 LLM 调用可长期查询；
3. 用户隔离、管理员隔离和 API Key 保护可检查；
4. 流式完成、失败、停止和页面中断后的最终状态明确；
5. 在单机上可安装、迁移、启动、验证和回滚；
6. 为未来 Agent 保留替换边界，但不提前承担 Agent 运行时成本。

## 3. 候选方案比较

| 维度 | TypeScript + Fastify | Python + FastAPI + OpenAI SDK | Python + FastAPI + LangGraph |
| --- | --- | --- | --- |
| 当前 P0 | 充分 | 充分 | 充分但过量 |
| OpenAPI/校验 | 需额外 schema 工具 | Pydantic/FastAPI 原生适配 | 同 FastAPI，另有 Graph State |
| 流式聊天 | 直接 SDK | 直接 SDK | 需再把 Graph 事件映射为产品 SSE |
| 当前状态模型 | 一套业务状态 | 一套业务状态 | 业务状态 + checkpoint 两套状态 |
| 单机部署 | 简单 | 简单 | 依赖和诊断面更大 |
| 后续 Agent 生态 | 可用 | Python 生态更直接 | 最强，但当前没有对应需求 |
| 迁移成本 | 后续可能换语言 | 仅替换 `GenerationEngine` | 现在即承担编排框架成本 |

最终选择 Python + FastAPI + OpenAI SDK。相比 TypeScript，它更贴近明确的长期 Agent
方向；相比现在引入 LangGraph，它只承担当前产品真正需要的复杂度。

## 4. P0 机制与延后机制

| 机制 | 决策 | P0 依据与代价 |
| --- | --- | --- |
| PostgreSQL | 保留 | 刷新/再登录后历史仍在，管理员需查 Prompt 与返回；单实例即可 |
| `generations` 状态表 | 保留 | 停止、失败、重试、页面中断后读取终态需要权威状态 |
| 进程内生成任务 | 保留 | 浏览器断线不能直接判失败；单 API 进程无需队列 |
| 启动时清理中断生成 | 保留 | 服务器重启后服务可恢复；旧生成标记失败并保留部分内容 |
| 持久化 SSE 事件表 | 移除 | PRD 只要求重新进入后看最终状态，不要求逐事件重放 |
| `/stream` 重放端点和 24 小时保留 | 移除 | 通过生成状态与消息查询恢复，少一张高写入表和清理任务 |
| 通用后台任务表 | 移除 | 标题失败允许保留临时标题，后续成功回复可再次尝试 |
| Redis/消息队列/独立 Worker | 延后 | 单机、单进程无容量指标；多实例或长任务出现时再引入 |
| `Idempotency-Key` + 请求指纹 | 移除 | 使用浏览器稳定 UUID 与数据库唯一约束即可防重复消息 |
| 签名 cursor | 移除 | P0 数据量无性能门槛；简单页码分页可直接测试和运维 |
| CSRF Token | 移除 | 同源部署、SameSite Cookie、Origin/Sec-Fetch-Site 与 JSON 类型检查足够 |
| LangGraph | 延后 | 工具调用、条件分支、人工审批或可恢复长任务出现时再引入 |

## 5. 系统上下文与部署

```text
Internet
   |
 Nginx :443
   |-- /            -> user-web static
   |-- /admin/      -> admin-web static
   `-- /api, /healthz -> FastAPI :3000
                              |-- PostgreSQL :5432
                              `-- OpenAI HTTPS
```

Nginx 对 SSE 路由关闭响应缓冲并设置合理的读取超时。FastAPI 以一个 Uvicorn worker
运行；生成任务注册表位于该进程内。这个限制与单机 MVP 一致，避免停止请求落到另一个
worker。未来需要多 worker 时，必须先把生成执行迁移到共享 Worker/队列。

生产环境只从 Secret/环境变量读取数据库密码和 API Key 加密主密钥。OpenAI API Key
由管理员在页面保存，加密后进入数据库，不进入前端构建产物、日志或仓库。

## 6. 模块边界

```text
littleduck_api/
  main.py          HTTP、Cookie、同源检查、SSE 适配
  config.py        无业务逻辑的环境配置
  models.py        PostgreSQL ORM 模型
  repository.py    权限范围内的事务和查询
  engine.py        GenerationEngine 端口与无凭据演示实现
  service.py       生成生命周期、停止和领域事件
  security.py      API Key AES-256-GCM 加解密
```

后续实现应继续按领域拆成 `user_auth`、`admin_auth`、`conversations`、`generations`、
`llm_config`、`admin_topics`，但保持一个可部署单体。路由不得直接操作 ORM；所有用户资源
查询都必须同时携带当前 `user_id`。

## 7. GenerationEngine 演进边界

```python
class GenerationEngine(Protocol):
    def stream(self, prompt: list[dict[str, str]]) -> AsyncIterator[str]: ...
```

当前实现由 OpenAI SDK 逐段输出。业务层只消费统一的 delta，不依赖供应商或未来框架
事件。出现以下需求时创建独立 Work Item，再增加 `LangGraphGenerationEngine`：

- 模型根据结果选择多个后续节点；
- 搜索、文件、数据库等工具调用；
- 人工审批后暂停和恢复；
- 进程重启后继续长任务；
- 多 Agent、checkpoint 或执行步骤 UI。

LangGraph 接入后仍不得把内部事件直接暴露给前端，也不得用 checkpoint 取代用户、
会话、消息、生成和 LLM 调用等业务权威数据。

## 8. 核心生成流程

### 8.1 创建生成

1. Cookie Session 得到当前 `user_id`；
2. 若传入 `conversationId`，用 `id + user_id` 查询，不存在或越权统一 404；
3. 锁定当前用户行，并用 `(user_id, clientMessageId)` 检查重复请求；
4. 单个数据库事务创建或更新会话、用户消息、助手占位、生成和 LLM 调用；
5. 事务提交后启动独立于 SSE 订阅者的进程内异步任务；
6. HTTP 返回 `generation.started`，随后转发 delta；
7. 每批 delta 更新助手部分内容和 LLM 调用部分返回；
8. 完成、失败或停止时，用一个事务写入三个对象的终态。

消息内容最多 4,000 字符。上下文按原始顺序使用最近的完整成功轮次；失败、停止内容
不作为成功助手上下文。实际发送的角色、顺序和内容在调用开始前写入 `llm_calls.prompt`。

### 8.2 重复提交

浏览器为一次发送生成一个 `clientMessageId`，网络重试必须复用。唯一约束冲突时返回
409 `DUPLICATE_MESSAGE` 和已有 `generationId`；客户端读取该生成状态，不再插入消息。
重试回复同理使用 `clientRetryId`，原失败/停止助手记录不覆盖。

### 8.3 停止

停止端点把 `stop_requested` 设为 true，并通知进程内任务。任务在下一个可取消点结束
供应商流，保留已聚合内容，并把生成、助手消息、LLM 调用写为 stopped。重复停止返回
当前状态，不创建新记录。

### 8.4 页面或网络中断

SSE 订阅者离开不取消生成任务。事件不做持久化重放：客户端重新进入后调用
`GET /generations/{generationId}` 和消息接口；若仍在 streaming，可短轮询状态，终态后用
已保存的助手内容渲染。该行为直接对应 PRD“以系统最终保存状态为准”。

### 8.5 进程重启

启动时把遗留 streaming 生成、助手消息和 LLM 调用标记为 failed，错误码为
`GENERATION_INTERRUPTED`，保留已接收部分内容。用户可按普通失败回复重试。MVP 不承诺
进程重启后续接同一次供应商流。

### 8.6 标题

首条消息事务内写前 20 个字符临时标题。首个成功助手回复后，在同一进程发起一次
非阻塞标题调用并记录 `llm_calls`。失败不影响聊天、无需任务表；后续成功回复发现标题
仍为 temporary 时可再次尝试。标题最终截断为最多 20 个字符。

## 9. 身份与安全边界

- 普通用户和管理员使用不同 Cookie 名、Path、Session 表和依赖函数；
- Session Token 使用 256 位随机值，数据库只存 SHA-256 哈希，默认 7 天；
- Cookie 使用 `HttpOnly; Secure; SameSite=Lax`；
- 写请求只接受 JSON，拒绝跨源 Origin 和跨站 `Sec-Fetch-Site`；Nginx 不开放任意 CORS；
- 用户查询必须包含 `user_id`，不存在和越权统一返回 404；
- 管理员密码存强哈希；初始化 `admin/admin` 是产品明确接受的临时风险；
- OpenAI API Key 用 AES-256-GCM 加密，nonce 随机，主密钥只在部署 Secret 中；
- 管理端按 PRD 解密并明文展示完整 Key，但响应禁止缓存且日志必须脱敏；
- 用户错误不暴露供应商错误，完整供应商错误只进入管理员可见调用记录。

## 10. 合同与实现关系

`contracts/openapi.yaml` 是产品行为合同；FastAPI 自动 OpenAPI 只能用于检查实现子集，
不得自动覆盖基线。React 类型从基线生成。SSE 只定义 LittleDuck 事件，不暴露 OpenAI
事件。合同接受后，路径、字段、状态码、错误码、分页、Cookie 和 SSE 语义的变化必须由
Coordinator 创建合同修订 Work Item。

合同共有 21 个 path、22 个 operation：1 个健康检查，11 个用户端 operation（认证 4、
会话/消息 3、生成/状态/停止/重试 4），10 个管理端 operation（认证 3、配置 3、话题查询
4）。`GET` 与 `PUT /api/v1/admin/llm-config` 共用一个 path，因此 operation 比 path 多 1。

## 11. 工程骨架证明范围

骨架实际实现并验证：

- FastAPI 启动和 PostgreSQL readiness；
- Alembic 在 PostgreSQL 16 上升级和回退；
- Cookie Session 用户解析和越权统一 404；
- 创建生成事务、真实 PostgreSQL 持久化、SSE delta 与完成终态；
- 重复 `clientMessageId` 不产生第二条生成；
- LLM 调用保存实际 Prompt 和聚合返回；
- API Key 加密往返；
- 实现路径是完整 OpenAPI 的合法子集。

骨架的 `DemoGenerationEngine` 不访问外部模型、不含真实凭据，也不代表完整产品业务已实现。
真实认证、全部查询、OpenAI provider、标题调用和部署由后续 Work Items 完成。

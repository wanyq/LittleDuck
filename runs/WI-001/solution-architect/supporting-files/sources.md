# 外部技术来源与方案推导

核对日期：2026-07-17。以下均为项目或供应商官方资料；版本由骨架锁文件固定，不依赖本文
中的“latest”描述。

1. OpenAI — [Text generation](https://platform.openai.com/docs/guides/text)
   - Responses API 可直接完成当前单轮/多轮文本生成。
   - 本方案把 SDK 封装在 `GenerationEngine` 后，公开合同不暴露供应商事件或对象。

2. OpenAI — [Streaming responses](https://platform.openai.com/docs/guides/streaming-responses)
   - 供应商在 `stream=true` 时发送 SSE 事件。
   - 本方案只把文本增量和终态翻译为较小的 `generation.*` 领域事件；供应商事件不能直接
     成为前端合同。

3. OpenAI — [Production best practices](https://platform.openai.com/docs/guides/production-best-practices)
   - API Key 应保持服务端私有，不写代码或公共仓库。
   - LittleDuck 还因“管理员可查看明文”的产品要求，在数据库中用 AES-256-GCM 可逆加密，
     主密钥只从部署环境注入。

4. FastAPI — [Concurrency and async/await](https://fastapi.tiangolo.com/async/)
   - 网络、数据库和远程 API 都是 I/O 等待型工作，适合 `async def` / `await`。
   - 这与 LittleDuck 的 PostgreSQL + 流式模型调用路径匹配，也减少跨语言 Agent 集成成本。

5. FastAPI — [Response classes and streaming](https://fastapi.tiangolo.com/reference/responses/)
   - FastAPI/Starlette 提供流式响应能力。
   - 骨架以异步迭代器生成 `text/event-stream`，并显式关闭代理缓冲。

6. SQLAlchemy — [AsyncIO support](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
   - SQLAlchemy 2 提供异步 Engine、Session 和 ORM 路径。
   - 骨架用同一事务创建会话、消息、generation 与 LLM call，并用 `user_id` 约束资源查询。

7. Alembic — [Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
   - Alembic 管理基于 SQLAlchemy 的关系数据库变更脚本。
   - 本 Run 不再只交付参考 SQL；migration 已在 PostgreSQL 16 上验证升级、回退和再升级。

8. PostgreSQL 16 — [Constraints](https://www.postgresql.org/docs/16/ddl-constraints.html)
   - 唯一约束可由数据库而非进程内状态强制执行。
   - `(user_id, client_request_id)` 是重复提交防护的最终一致性边界。

9. LangGraph — [Overview](https://docs.langchain.com/oss/python/langgraph/overview)
   - 官方把 LangGraph 定位为长运行、有状态 Agent 的低层编排运行时，核心价值是 durable
     execution、human-in-the-loop、memory 与 persistence。
   - 当前需求只有一个模型生成步骤，无工具、条件路由、人工审批或 checkpoint 恢复；引入图
     只会增加状态与持久化体系。因此 P0 不依赖 LangGraph。

10. LangGraph — [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
    - checkpoint 主要支持人工介入、记忆、time travel 和故障恢复。
    - 当 LittleDuck 出现多步工具链、可暂停审批、长任务续跑或多 Agent 协作时，再创建合同
      修订/架构演进 Work Item，并在 `GenerationEngine` 内接入图运行时。

结论：Python/FastAPI + 官方 OpenAI SDK 是当前最小充分方案；保留接口边界即可获得未来迁移
能力，无需为尚不存在的 Agent 工作流预付 LangGraph 的运行时和双重状态成本。

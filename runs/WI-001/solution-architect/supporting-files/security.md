# LittleDuck MVP 认证、授权与凭据安全

## 1. 身份域隔离

| 项目 | 普通用户 | 管理员 |
| --- | --- | --- |
| API 前缀 | `/api/v1/user` | `/api/v1/admin` |
| Cookie | `ld_user_session` | `ld_admin_session` |
| Cookie Path | `/api/v1/user` | `/api/v1/admin` |
| Session 表 | `user_sessions` | `admin_sessions` |
| 认证依赖 | `require_user` | `require_admin` |

普通用户 Cookie 不能访问管理员路由，管理员 Cookie 也不能代替用户 Cookie。前端页面隐藏
不是权限控制；每个受保护路由必须执行对应服务端依赖。

## 2. Session

- 登录生成至少 256 位随机 Token；
- 浏览器 Cookie：`HttpOnly; Secure; SameSite=Lax`；
- 数据库只保存 `SHA-256(token)`、主体 ID、到期和撤销时间；
- 默认登录期 7 天；同一用户允许多个 Session；
- 认证 Principal 同时保留主体 ID 与精确 Session ID；
- generation 非空关联 `initiating_session_id`；退出仅撤销当前 Session、只停止该 Session
  发起的 streaming generation，并清除对应 Cookie；同账号其他 Session 不受影响；
- 响应和日志不得输出 Token、验证码、Cookie 或完整手机号。

固定验证码 `000000` 和初始管理员 `admin/admin` 是 PRD 明确接受的 MVP 风险，不得误写成
生产级身份认证。骨架用 memory-hard scrypt（随机 salt、参数随哈希保存）存储管理员密码。
部署 Work Item 必须在 migration 后运行 `api:bootstrap-admin`；入口使用数据库唯一约束和
`ON CONFLICT DO NOTHING`，首次创建 `admin/admin`，重复执行不覆盖人工修改后的强哈希。

## 3. 写请求的跨站防护

本期不发放独立 CSRF Token，因为用户端、管理端和 API 均由同一站点的 Nginx 提供。写
请求同时执行：

1. Cookie 使用 `SameSite=Lax`；
2. 有 `Origin` 时必须精确匹配对应用户端或管理端 origin；
3. 有 `Sec-Fetch-Site` 时只允许 `same-origin` 或 `none`；
4. 有请求体的 mutation 只接受 `application/json`；
5. 不开放带凭据的任意 CORS；
6. 对登录和敏感配置接口做频率限制。

普通跨站 HTML form 无法构造被接受的 JSON 请求；现代浏览器的 Origin/Fetch Metadata 再阻止
跨站提交。若未来前端/API 跨站部署、支持老旧浏览器或增加 form 上传，必须重新评估并通过
合同修订增加 CSRF Token。

## 4. 会话越权防护

所有用户资源使用“资源 ID + 当前用户 ID”查询：

```sql
SELECT *
FROM conversations
WHERE id = :conversation_id
  AND user_id = :current_user_id;
```

消息、生成和停止操作必须经 conversation 或 generation 的 `user_id` 过滤。对“不存在”和
“属于别人”统一返回 404 `RESOURCE_NOT_FOUND`，避免确认资源存在。不得先按 ID 查询后在
Python 中判断所有者。

管理员通过独立依赖读取跨用户话题；管理员接口只读聊天和 LLM 调用，不能由用户 Cookie
访问。

## 5. 重复提交和并发

- 新消息请求必须带浏览器生成的 `clientMessageId` UUID；
- 数据库唯一约束 `(user_id, client_request_id)` 防止弱网和重复点击写入两次；
- 冲突返回 409 `DUPLICATE_MESSAGE` 和已有 `generationId`；
- 重试使用新的 `clientRetryId`，语义相同；
- 停止端点天然幂等，终态重复停止只返回当前状态；
- logout 与创建 generation 都锁定并重验精确 Session，避免认证后并发退出留下失控任务；
- 同一会话存在 streaming generation 时拒绝新生成。

这比通用 `Idempotency-Key`、请求指纹和过期清理表更符合当前三个 mutation 场景。

## 6. OpenAI API Key

为满足管理员明文查看要求，Key 不能单向哈希：

- 使用 AES-256-GCM；
- 每次保存生成 96 位随机 nonce；
- 数据库存 ciphertext 与 nonce；
- 32 字节主密钥仅从生产 Secret/环境变量注入，不入库、不入 Git；
- 解密只发生在管理员读取和服务端 OpenAI 调用；
- 配置读取响应使用 `Cache-Control: no-store`；
- 日志、异常、监控属性和测试快照不得包含 Key；
- 骨架用随机测试密钥验证往返，不提交固定密钥。

## 7. LLM 调用与错误

普通用户只看到稳定错误，例如 `LLM_UNAVAILABLE`、`LLM_TIMEOUT`；不得看到 API Key、供应商
响应头或内部堆栈。管理员调用详情可查看实际 Prompt、完整/部分返回和经筛选的供应商错误，
但仍不显示请求头或 API Key。

Prompt 在调用开始前保存；响应按批次聚合；完成、失败、停止都保存实际已收到内容。测试
连接不写入用户话题调用记录。

## 8. HTTP 与部署

- 生产只开放 HTTPS；HTTP 重定向 HTTPS；
- Nginx 增加 HSTS、`X-Content-Type-Options: nosniff`、合理 CSP 和 Referrer-Policy；
- API、配置和认证响应禁止共享缓存；静态 hashed assets 可长期缓存；
- SSE 路由关闭代理缓冲；
- 数据库只监听本机或私网，不公网开放；
- 进程使用非 root 用户，环境文件权限最小化；
- 日志记录 request ID、路由、状态、耗时和内部对象 ID，不记录正文、Prompt、返回、Cookie 或 Key。

## 9. 骨架可检查项

- Cookie Session 解析和过期/撤销条件；
- 用户 A 请求用户 B generation 返回 404；
- 相同 `clientMessageId` 只保存一个 generation；
- 非同源 Origin / Fetch Metadata 被拒绝；
- API Key AES-GCM 往返且 ciphertext 不含明文；
- 初始管理员只保存强哈希，bootstrap 重跑不产生重复行或重置密码；
- 同用户双 Session 退出只撤销/停止当前 Session 的对象；
- 实际 JSON/SSE 由 OpenAPI 封闭 Schema 校验，所有对外时间递归校验为 UTC；
- secret scanner 不发现私钥、Token 或生产凭据。

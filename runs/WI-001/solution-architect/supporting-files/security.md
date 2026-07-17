# 认证、授权与凭据安全设计

## 1. 身份域隔离

| 身份域 | API 前缀 | Cookie | Cookie Path | 会话表 |
| --- | --- | --- | --- | --- |
| 普通用户 | `/api/v1/user` | `ld_user_session` | `/api/v1/user` | `user_sessions` |
| 管理员 | `/api/v1/admin` | `ld_admin_session` | `/api/v1/admin` | `admin_sessions` |

- 两个 Cookie 名称、路径、签发逻辑和中间件不同。
- 管理端绝不接受普通用户 Cookie 作为身份。
- 用户端绝不接受管理员 Cookie 作为用户身份。
- 前端路由守卫仅改善体验，服务端授权才是安全边界。

## 2. Cookie 和 Session

生产 Cookie 属性：

```text
HttpOnly; Secure; SameSite=Lax; Path=<identity namespace>
```

- Token 为 256-bit CSPRNG 随机值。
- 数据库只保存 Token SHA-256 哈希。
- 用户登录态绝对有效期 7 天。
- 同一账号多设备会话并存。
- 退出撤销当前 Token，并清除当前身份域 Cookie。
- 用户端敏感页面返回 `Cache-Control: no-store`。

## 3. CSRF

- 登录和注册端点要求同源 `Origin`/`Referer`、JSON Content-Type 和受限 CORS。
- 登录后响应返回随机 CSRF Token；服务端只保存其哈希。
- 所有已认证且有副作用的请求必须携带 `X-CSRF-Token`。
- SSE 创建和重试使用 POST，因此也必须带 CSRF Token。
- GET 恢复流只读，不要求 CSRF，但仍要求用户 Cookie 和资源归属。

## 4. 输入和错误

- 手机号仅允许中国大陆 11 位数字。
- 验证码必须为 6 位；仅 `000000` 通过。
- 用户消息 trim 后长度 1–4000 Unicode 字符。
- 所有 ID、cursor、日期、分页和枚举由 Schema 校验。
- 普通用户错误不得包含完整手机号、验证码、OpenAI API Key、模型服务原始错误、数据库错误或堆栈。
- 管理员配置测试与 LLM 调用详情可展示供应商错误，但服务端必须在持久化与响应前剔除 Authorization header、API Key 和请求头。

## 5. 会话越权防护

每个用户资源查询都必须把 `current_user_id` 纳入 SQL 条件：

- conversation；
- message；
- generation；
- SSE replay；
- stop；
- retry。

不存在与不属于当前用户统一返回：

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "资源不存在"
  }
}
```

不得通过不同状态码、耗时或错误信息暴露资源是否属于其他用户。

## 6. 管理员密码

- 初始化命令把 `admin/admin` 写为 Argon2id 哈希。
- 环境允许时首次启动后仍保持 PRD 指定凭据，不擅自要求改密。
- 登录错误统一为 `INVALID_CREDENTIALS`。
- 不记录密码、请求体或认证 Header。

## 7. OpenAI API Key

PRD 要求管理员可明文查看，因此不能只做单向哈希：

- 数据库使用 AES-256-GCM 加密；
- 主密钥来自 `CONFIG_ENCRYPTION_KEY`，不进入数据库或 Git；
- 明文只在认证管理员读取配置、测试连接或发起供应商调用时短暂存在于进程内存；
- 日志、追踪、错误和 `llm_calls` 均禁止记录 Key；
- 生产环境通过 Secret 管理或受限环境变量注入；
- `.env.example` 只提供占位符。

OpenAI 官方生产指南也要求避免把 API Key 暴露在代码或公开仓库中，并建议通过环境变量或 Secret 管理服务注入。

## 8. 浏览器与 HTTP 安全

- 生产只允许 HTTPS。
- `Content-Security-Policy` 默认同源；连接仅允许自身 API。
- `X-Content-Type-Options: nosniff`。
- `Referrer-Policy: same-origin`。
- `frame-ancestors 'none'`。
- Markdown 禁止原始 HTML，链接增加安全属性，代码块仅文本渲染。
- Nginx 和 API 都限制请求体大小。
- SSE 响应使用 `Cache-Control: no-cache, no-transform` 和 `X-Accel-Buffering: no`。

## 9. 日志与可观测性

允许记录：

- request id；
- route 模板、状态码、耗时；
- user/admin 内部 UUID（必要时）；
- generation/llm_call ID；
- 归一化错误码。

禁止记录：

- Cookie、Authorization、CSRF Token；
- API Key 和加密主密钥；
- 验证码；
- 登录请求体；
- Prompt、聊天正文和 LLM 返回的默认全文。

Prompt 和返回只保存在受管理端权限保护的数据库业务记录中。

## 10. 已接受的 MVP 风险

- `000000` 不能证明手机号所有权；
- `admin/admin` 安全性弱；
- API Key 在管理端明文展示；
- 无管理员审计、VPN 或 IP 白名单；
- 无内容安全能力。

这些是 PRD 明确接受的产品风险。实现不得暗中扩大风险，例如把 Key 放进前端、日志或 Git。

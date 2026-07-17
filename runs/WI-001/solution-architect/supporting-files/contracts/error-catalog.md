# 错误码与 HTTP 语义

所有普通 JSON 错误使用：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不正确",
    "requestId": "req_01",
    "details": [
      {"field": "content", "issue": "长度必须为 1 到 4000 个字符"}
    ]
  }
}
```

| HTTP | code | 使用场景 |
| --- | --- | --- |
| 400 | `VALIDATION_ERROR` | Schema、路径、header 或 body 非法 |
| 400 | `INVALID_VERIFICATION_CODE` | 验证码不是 `000000` |
| 400 | `CURSOR_INVALID` | cursor、after 或 Last-Event-ID 非法 |
| 400 | `DATE_RANGE_INVALID` | 管理端日期范围反向或超出允许格式 |
| 401 | `INVALID_CREDENTIALS` | 管理员账号或密码错误 |
| 401 | `UNAUTHENTICATED` | Cookie 缺失、过期或撤销 |
| 403 | `FORBIDDEN` | CSRF、Origin 或身份域检查失败 |
| 404 | `USER_NOT_REGISTERED` | 用户登录手机号未注册 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在或不属于当前用户 |
| 409 | `USER_ALREADY_EXISTS` | 重复注册 |
| 409 | `GENERATION_IN_PROGRESS` | 当前会话已有活动生成 |
| 409 | `RETRY_NOT_ALLOWED` | 目标不是最新可重试失败/停止回复 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同一 key 对应不同请求指纹 |
| 410 | `STREAM_REPLAY_EXPIRED` | 流事件已清理，需刷新最终消息 |
| 429 | `RATE_LIMITED` | 应用或供应商前置限流 |
| 503 | `LLM_NOT_CONFIGURED` | 尚未保存生效配置 |
| 503 | `LLM_UNAVAILABLE` | 流建立前服务不可用 |
| 500 | `INTERNAL_ERROR` | 未分类服务端错误 |

## 流内错误

SSE 建立后不再改变 HTTP 状态。业务失败使用 `generation.failed`，其公开错误码仅允许：

- `LLM_NOT_CONFIGURED`
- `LLM_UNAVAILABLE`
- `LLM_RATE_LIMITED`
- `LLM_TIMEOUT`
- `RESPONSE_PARSE_FAILED`
- `GENERATION_INTERRUPTED`

供应商原始错误只写入管理员可见 `llm_calls.providerError`。

## 隐私规则

- 越权和不存在都返回 404 `RESOURCE_NOT_FOUND`。
- 普通用户错误不出现完整手机号、验证码、API Key、模型供应商原始错误、SQL 或堆栈。
- `requestId` 用于日志关联，不包含用户或凭据信息。

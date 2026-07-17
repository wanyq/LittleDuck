# 错误码与 HTTP 语义

普通 JSON 错误统一为：

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
| 400 | `VALIDATION_ERROR` | Schema、路径、query 或 body 非法；正文按 trim 后 1..4000 校验，或当前输入本身超过模型输入预算 |
| 400 | `INVALID_VERIFICATION_CODE` | 验证码不是 `000000` |
| 400 | `PAGE_INVALID` | `page` 或 `pageSize` 超出合同范围 |
| 400 | `DATE_RANGE_INVALID` | 管理端日期范围反向或格式非法 |
| 401 | `INVALID_CREDENTIALS` | 管理员账号或密码错误 |
| 401 | `UNAUTHENTICATED` | 对应身份域 Cookie 缺失、过期或撤销 |
| 403 | `FORBIDDEN` | Origin、Sec-Fetch-Site、身份域或授权检查失败 |
| 404 | `USER_NOT_REGISTERED` | 用户登录手机号未注册 |
| 404 | `RESOURCE_NOT_FOUND` | 资源不存在或不属于当前用户 |
| 409 | `USER_ALREADY_EXISTS` | 重复注册 |
| 409 | `GENERATION_IN_PROGRESS` | 当前会话已有活动生成 |
| 409 | `RETRY_NOT_ALLOWED` | 目标不是最新可重试失败/停止回复 |
| 409 | `DUPLICATE_MESSAGE` | 同一用户重复提交稳定客户端 UUID；附已有 `generationId` |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | 有 body 的 mutation 不是 `application/json` |
| 429 | `RATE_LIMITED` | 应用或供应商前置限流 |
| 503 | `LLM_NOT_CONFIGURED` | 尚未保存生效配置 |
| 503 | `LLM_UNAVAILABLE` | 流建立前服务不可用 |
| 500 | `INTERNAL_ERROR` | 未分类服务端错误；公开响应不含内部细节 |

## 流内错误

SSE 响应建立后不再改变 HTTP 状态。业务失败以唯一终态 `generation.failed` 表达，
公开错误码仅允许：

- `LLM_NOT_CONFIGURED`
- `LLM_UNAVAILABLE`
- `LLM_RATE_LIMITED`
- `LLM_TIMEOUT`
- `RESPONSE_PARSE_FAILED`
- `GENERATION_INTERRUPTED`

所有 `Generation` JSON 形状固定包含 `errorCode`：streaming/completed/stopped 为 `null`，
failed 为上述公开码，且与 `generation.failed.error.code` 一致。`finishedAt` 在 streaming 时为
`null`，进入任一终态后为 UTC date-time。

供应商原始错误只进入管理员可见的 `llm_calls.providerError`。浏览器断线不是业务错误；
重新进入页面后读取生成状态和消息，不存在流重放错误码。

## 隐私与重试规则

- 越权与不存在统一返回 404 `RESOURCE_NOT_FOUND`，避免资源枚举。
- 401 只表示当前身份域未认证；用户 Cookie 不能认证管理端，反之亦然。
- 只有合同明确标为可重试的流内错误或失败/停止消息才展示重试入口。
- 普通用户错误不出现完整手机号、验证码、API Key、供应商原始错误、SQL 或堆栈。
- `requestId` 只用于日志关联，不编码用户或凭据信息。

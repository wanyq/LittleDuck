# LittleDuck MVP UI 文案清单

## 1. 用户端认证

| ID | 场景 | 文案 |
| --- | --- | --- |
| AUTH-PHONE-LABEL | 字段 | 手机号 |
| AUTH-PHONE-PH | 占位 | 请输入手机号 |
| AUTH-CODE-LABEL | 字段 | 验证码 |
| AUTH-CODE-PH | 占位 | 请输入6位验证码 |
| AUTH-CODE-GET | 按钮 | 获取验证码 |
| AUTH-CODE-GOT | 点击后 | 验证码已获取 |
| AUTH-PHONE-INVALID | 校验 | 请输入正确的11位手机号 |
| AUTH-CODE-INVALID | 校验 | 验证码错误，请重新输入 |
| REGISTER-ACTION | 按钮 | 注册 |
| REGISTER-LOADING | 提交中 | 注册中… |
| REGISTER-SUCCESS | 成功 | 注册成功 |
| REGISTER-EXISTS | 业务错误 | 该手机号已注册，请直接登录 |
| REGISTER-TO-LOGIN | 链接 | 去登录 |
| LOGIN-ACTION | 按钮 | 登录 |
| LOGIN-LOADING | 提交中 | 登录中… |
| LOGIN-SUCCESS | 成功 | 登录成功 |
| LOGIN-NOT-REGISTERED | 业务错误 | 该手机号尚未注册，请先注册 |
| LOGIN-TO-REGISTER | 链接 | 去注册 |
| LOGIN-EXPIRED | 登录失效 | 登录已失效，请重新登录 |
| AUTH-NETWORK-ERROR | 网络失败 | 网络连接失败，请检查网络后重试 |

## 2. 用户端聊天

| ID | 场景 | 文案 |
| --- | --- | --- |
| CHAT-WELCOME | 新对话静态欢迎 | 你好！有什么可以帮助你？ |
| CHAT-INPUT-PH | 输入框 | 输入消息…… |
| CHAT-COUNT-LEFT | 3,800–4,000 字 | 剩余 {count} 字 |
| CHAT-COUNT-OVER | 超限 | 已超出 {count} 个字符 |
| CHAT-SEND | 无障碍名称 | 发送消息 |
| CHAT-STOP | 无障碍名称 | 停止生成 |
| CHAT-GENERATING | 生成中 | 正在生成 |
| CHAT-STOPPED | 状态 | 已停止 |
| CHAT-REPLY-FAILED | 普通失败 | 回复生成失败，请稍后重试 |
| CHAT-SERVICE-UNAVAILABLE | 配置/服务异常 | 服务暂时不可用，请稍后再试 |
| CHAT-USER-SEND-FAILED | 用户消息失败 | 发送失败 |
| CHAT-RESEND | 用户消息操作 | 重新发送 |
| CHAT-RETRY | 助手消息操作 | 重试 |
| CHAT-LOAD-FAILED | 会话加载失败 | 对话加载失败 |
| CHAT-RELOAD | 恢复操作 | 重新加载 |
| CHAT-OFFLINE | 断网 | 网络已断开 |
| CHAT-BACK-BOTTOM | 浮动按钮 | 回到底部 |
| CHAT-LOAD-EARLIER | 历史分页 | 正在加载更早消息… |

## 3. 历史侧边栏

| ID | 场景 | 文案 |
| --- | --- | --- |
| DRAWER-TITLE | 标题 | 聊天记录 |
| DRAWER-NEW | 按钮 | 新对话 |
| DRAWER-SEARCH-PH | 搜索 | 搜索对话 |
| DRAWER-GROUP-TODAY | 分组 | 今天 |
| DRAWER-GROUP-YESTERDAY | 分组 | 昨天 |
| DRAWER-GROUP-7D | 分组 | 最近7天 |
| DRAWER-GROUP-OLDER | 分组 | 更早 |
| DRAWER-EMPTY | 无历史 | 还没有历史对话 |
| DRAWER-NO-RESULT | 搜索无结果 | 未找到相关对话 |
| DRAWER-CLEAR | 搜索恢复 | 清空搜索 |
| DRAWER-LOAD-FAILED | 增量失败 | 加载失败，点击重试 |
| DRAWER-GENERATING-LOCK | 生成锁定 | 请等待回复完成或先停止生成 |
| DRAWER-LOGOUT | 底部动作 | 退出登录 |

## 4. 管理端通用

| ID | 场景 | 文案 |
| --- | --- | --- |
| ADMIN-BRAND | 品牌 | LittleDuck 管理端 |
| ADMIN-MENU-CONFIG | 导航 | LLM 配置 |
| ADMIN-MENU-CHATS | 导航 | 聊天记录 |
| ADMIN-LOGOUT | 导航 | 退出登录 |
| COMMON-RETRY | 通用 | 重新加载 |
| COMMON-QUERY | 查询 | 查询 |
| COMMON-RESET | 查询 | 重置 |
| COMMON-COPY | 内容操作 | 复制 |
| COMMON-COPY-CODE | 代码操作 | 复制代码 |
| COMMON-COPIED | Toast | 已复制 |
| COMMON-EXPAND | 长内容 | 展开全部 |
| COMMON-COLLAPSE | 长内容 | 收起 |
| COMMON-NETWORK-ERROR | 网络 | 网络连接失败，请稍后重试 |

## 5. 管理员登录

| ID | 场景 | 文案 |
| --- | --- | --- |
| ADMIN-LOGIN-TITLE | 标题 | 管理员登录 |
| ADMIN-ACCOUNT | 字段 | 管理员账号 |
| ADMIN-PASSWORD | 字段 | 密码 |
| ADMIN-LOGIN-ACTION | 按钮 | 登录 |
| ADMIN-LOGIN-LOADING | 登录中 | 登录中… |
| ADMIN-LOGIN-INVALID | 认证失败 | 账号或密码错误 |

## 6. LLM 配置

| ID | 场景 | 文案 |
| --- | --- | --- |
| CONFIG-TITLE | 标题 | LLM 配置 |
| CONFIG-DESC | 说明 | 配置将用于后续聊天回复、会话标题生成和重试 |
| CONFIG-PROVIDER | 字段 | LLM 服务商 |
| CONFIG-API-KEY | 字段 | API Key |
| CONFIG-MODEL | 字段 | 模型 |
| CONFIG-EMPTY | 首次 | 尚未配置，请填写 API Key 和模型 |
| CONFIG-DIRTY | 编辑中 | 有未保存的修改 |
| CONFIG-TEST | 按钮 | 测试连接 |
| CONFIG-TESTING | 测试中 | 测试中… |
| CONFIG-TEST-FEE | 提示 | 测试可能产生少量模型费用 |
| CONFIG-TEST-SUCCESS | 成功 | 连接成功 |
| CONFIG-TEST-FAILED-SUFFIX | 失败补充 | 仍可保存当前配置 |
| CONFIG-SAVE | 按钮 | 保存 |
| CONFIG-SAVING | 保存中 | 保存中… |
| CONFIG-SAVE-SUCCESS | Toast | 配置已保存并立即生效 |
| CONFIG-SAVE-FAILED | 失败 | 保存失败，请重试 |
| CONFIG-API-KEY-REQUIRED | 必填 | 请输入 API Key |
| CONFIG-MODEL-REQUIRED | 必填 | 请输入模型 |

## 7. 话题列表与详情

| ID | 场景 | 文案 |
| --- | --- | --- |
| TOPIC-TITLE | 页面 | 聊天记录 |
| TOPIC-SEARCH-TITLE | 筛选 | 话题标题 |
| TOPIC-SEARCH-PHONE | 筛选 | 用户手机号 |
| TOPIC-DATE-TYPE | 筛选 | 日期类型 |
| TOPIC-DATE-CREATED | 选项 | 创建日期 |
| TOPIC-DATE-LATEST | 选项 | 最近消息日期 |
| TOPIC-EMPTY | 全局空态 | 暂无话题 |
| TOPIC-NO-RESULT | 筛选空态 | 未找到符合条件的话题 |
| TOPIC-RESET-FILTER | 恢复 | 重置筛选 |
| TOPIC-LOAD-FAILED | 失败 | 话题加载失败 |
| TOPIC-COL-TITLE | 表头 | 话题标题 |
| TOPIC-COL-PHONE | 表头 | 用户手机号 |
| TOPIC-COL-MESSAGES | 表头 | 消息数量 |
| TOPIC-COL-CALLS | 表头 | LLM 调用次数 |
| TOPIC-COL-CREATED | 表头 | 创建时间 |
| TOPIC-COL-LATEST | 表头 | 最近消息时间 |
| DETAIL-TAB-CHAT | 页签 | 聊天记录 |
| DETAIL-TAB-CALLS | 页签 | LLM 调用详情 |
| DETAIL-CHAT-EMPTY | 空态 | 暂无聊天记录 |
| DETAIL-CHAT-FAILED | 失败 | 聊天记录加载失败 |
| DETAIL-CALL-EMPTY | 空态 | 暂无 LLM 调用记录 |
| DETAIL-CALL-FAILED | 失败 | LLM 调用记录加载失败 |
| CALL-STEP | 调用卡 | 步骤 {number} |
| CALL-RELATED | 字段 | 关联内容 |
| CALL-TIME | 字段 | 调用时间 |
| CALL-PROVIDER-MODEL | 字段 | 服务商 / 模型 |
| CALL-PROMPT | 字段 | Prompt |
| CALL-RETURN | 字段 | LLM 返回内容 |
| CALL-ERROR | 字段 | 错误信息 |
| CALL-TYPE-CHAT | 类型 | 聊天回复 |
| CALL-TYPE-TITLE | 类型 | 会话标题生成 |
| CALL-TYPE-RETRY | 类型 | 重试 |
| STATUS-IN-PROGRESS | 状态 | 进行中 |
| STATUS-SUCCESS | 状态 | 成功 |
| STATUS-FAILED | 状态 | 失败 |
| STATUS-STOPPED | 状态 | 已停止 |


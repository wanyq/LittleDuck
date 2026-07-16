# WI-002 用户端与管理端 UX/UI 规格

## 结论

已依据 PRD V1.7 与 `/页面UI稿` 完成 LittleDuck MVP 的用户端 H5 和 PC Web 管理端完整 UX/UI 规格。

交付保持现有 UI 的核心方向：鸭子品牌、绿色主色、高留白、圆角和轻边框；补齐了基准稿未覆盖的加载、空态、失败、生成、停止和重试状态，并明确隐藏图片、附件及“+”等多模态入口。管理端采用适合 1280 px 及以上桌面浏览器的左侧导航 + 右侧内容布局，没有增加 PRD 范围外功能。

## 覆盖范围

- 注册、登录的默认、合法输入、验证码已获取、字段错误、账号状态、提交中、网络失败和成功状态；
- 聊天的新对话空态、页面加载、消息发送、流式生成、停止、失败、重试、断网、登录失效和历史分页状态；
- 375–430 px H5 的动态视口、软键盘、安全区、抽屉、滚动、横屏和字体放大规则；
- 历史侧边栏的时间分组、搜索、无结果、增量加载/失败、当前会话和生成中锁定状态；
- 管理员登录、LLM 配置、话题列表、聊天详情和 LLM 调用详情；
- PC 长文本、代码块、Prompt/返回内容的折叠、滚动、复制和状态徽标；
- 可供前端实现与 QA 编写用例的状态迁移、尺寸、组件、交互、响应式和文案定义。

## 交付索引

1. [`supporting-files/ux-ui-spec.md`](supporting-files/ux-ui-spec.md)

   完整 UX/UI 总规格，包含视觉 Token、H5/PC 布局、全部状态、交互规则、状态迁移、实现检查点与 QA 映射。

2. [`supporting-files/copy-catalog.md`](supporting-files/copy-catalog.md)

   用户端与管理端文案清单，按稳定 ID、场景和最终文案组织。

3. [`supporting-files/h5-visual-board.html`](supporting-files/h5-visual-board.html)

   可直接浏览的 H5 状态视觉板源码，覆盖认证错误、新对话、流式生成、停止/失败/重试、历史抽屉和软键盘安全区。

4. [`supporting-files/h5-visual-board.png`](supporting-files/h5-visual-board.png)

   经 Chrome 1580 × 2320 无头渲染并视觉检查的 H5 视觉板。

5. [`supporting-files/admin-visual-board.html`](supporting-files/admin-visual-board.html)

   可直接浏览的 PC 管理端视觉板源码，覆盖管理员登录、LLM 配置、话题列表、聊天详情和 LLM 调用详情。

6. [`supporting-files/admin-visual-board.png`](supporting-files/admin-visual-board.png)

   经 Chrome 1800 × 2860 无头渲染并视觉检查的 PC 管理端视觉板。

## 关键实现约束

- H5 输入区只保留纯文本输入和发送/停止按钮。
- 首条用户消息保存成功后才创建会话；发送失败不进入历史列表。
- 重试不重复用户消息，原失败/停止助手记录保留，新回复追加。
- 生成中可打开和搜索侧边栏，但不能切换会话或进入新对话。
- 软键盘使用 `100dvh`/`visualViewport` 等效方案保证输入区不被遮挡。
- 管理端测试连接失败仍允许保存；保存成功后立即用于后续业务调用。
- Prompt 只展示实际存在的角色与内容，不补造 System Prompt 或原始 API 请求体。

## 验证

- 两张 HTML 视觉板均由本机 Chrome 无头渲染为 PNG；
- 已检查 PNG 完整性、页面无截断、核心状态可读；
- 已执行 `git diff --check`，未发现空白符错误；
- 交付不包含真实 API Key、SSH 私钥、Token 或生产凭据。

# WI-002 revision 6 用户端与管理端完整 UX/UI 交付

## 结论

已依据 PRD V1.7、`页面UI稿/用户端UI` 的 5 张正式稿和 `页面UI稿/管理端UI` 的 6 张正式稿，完整重做 LittleDuck MVP 用户端 H5 与 PC Web 管理端规格。

本次交付以 11 张正式稿为主要视觉基准，保留鸭子 Logo、绿色品牌色、白/浅灰画布、圆角、低阴影、侧栏、表格、页签和步骤轴；补齐设计稿未覆盖的加载、空态、失败、生成、停止、重试、表单校验和恢复路径。所有偏差均来自 PRD 冲突或缺失状态，不新增范围外能力。

## 完成范围

- 用户端注册、登录、聊天和历史抽屉的完整状态、迁移、文案和恢复动作；
- 375–430 CSS px H5 的软键盘、安全区、动态视口、抽屉锁定、消息滚动、历史分页、横屏和字体放大规则；
- 管理员登录、LLM 配置、话题列表、聊天记录详情和 LLM 调用详情的 PC 规格；
- 管理端骨架、空态、无结果、失败、按钮加载/禁用、校验、Toast、长文本折叠、代码滚动和复制；
- 11 张输入逐项映射、PRD 例外和设计取舍；
- HTML 高保真视觉板、PNG 渲染结果、可复现渲染脚本和自动验证脚本。

## 关键决策

- H5 最终输入区只有纯文本框与发送/停止按钮；原稿的“+”和图片入口不实现。
- 话题列表沿用正式稿表格与分页控件，但默认改为 PRD 要求的每页 20 条。
- API Key 以完整明文呈现；交付只使用明确假的 `EXAMPLE_NOT_A_REAL_OPENAI_API_KEY_000000`，不采用掩码或类似真实格式的示例。
- Prompt 按该次调用真实角色与顺序展示；没有 System Prompt 时不渲染 system 行，也不补原始请求体。
- 管理端只读；不增加编辑、删除、下载、更多菜单、Prompt 修改或重新发起用户对话。
- 组件补充稿中的骨架、空态、失败、校验、Toast、折叠和复制被采用；范围外动作与 API Key 掩码样例被排除。

## 交付索引

1. [`supporting-files/ux-ui-spec.md`](supporting-files/ux-ui-spec.md)：完整 H5/PC 规格、状态、迁移、尺寸、交互、响应式、可访问性与 QA 映射。
2. [`supporting-files/copy-catalog.md`](supporting-files/copy-catalog.md)：按稳定 ID 组织的用户端和管理端最终文案。
3. [`supporting-files/input-mapping.md`](supporting-files/input-mapping.md)：5 张用户端 + 6 张管理端输入到最终页面、组件和状态的逐项映射。
4. [`supporting-files/design-decisions.md`](supporting-files/design-decisions.md)：PRD 例外、正式稿取舍和未新增能力声明。
5. [`supporting-files/littleduck-logo.svg`](supporting-files/littleduck-logo.svg)：最终补稿统一使用的可复用鸭子品牌矢量资产，保留羽冠、眼睛高光、橙色鸭嘴与绿色外形。
6. [`supporting-files/h5-visual-board.html`](supporting-files/h5-visual-board.html)：H5 高保真基准与最终状态补稿源码。
7. [`supporting-files/h5-visual-board.png`](supporting-files/h5-visual-board.png)：1680 × 3200 Chrome 渲染结果。
8. [`supporting-files/admin-visual-board.html`](supporting-files/admin-visual-board.html)：PC 管理端高保真基准、最终页面和状态矩阵源码。
9. [`supporting-files/admin-visual-board.png`](supporting-files/admin-visual-board.png)：1800 × 5900 Chrome 渲染结果。
10. [`supporting-files/scripts/render-boards.sh`](supporting-files/scripts/render-boards.sh)：可重复执行的两板渲染脚本。
11. [`supporting-files/scripts/validate-delivery.sh`](supporting-files/scripts/validate-delivery.sh)：输入映射、内容、尺寸、正式 Logo 使用与凭据模式自动检查。
12. [`supporting-files/self-test.md`](supporting-files/self-test.md)：环境、步骤、自动结果、人工视觉检查和已知限制。

## 验证结论

- 两张 PNG 均由交付内 HTML 直接渲染，无手工后期修改；
- 11 张正式输入全部映射，无遗漏页面；
- H5 最终补稿覆盖加载、空态、发送失败、生成、停止、重试、抽屉锁定、断网、键盘和安全区；
- PC 最终补稿覆盖登录错误、配置测试/保存、20 条分页、聊天多状态、真实 Prompt、空态、失败和复制；
- H5 注册/导航/欢迎/助手头像/抽屉与管理端登录/侧栏已统一使用 `littleduck-logo.svg`，不再存在抽象 CSS 圆环 Logo；
- `validate-delivery.sh` 全部通过；凭据模式扫描未发现私钥、Token 或疑似真实 API Key；
- 原始正式稿缩略图只作为输入映射证据，所有 PRD 冲突均有黄色标注；最终实现以“最终实现补稿”和 `ux-ui-spec.md` 为准。

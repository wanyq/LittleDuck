# WI-002 revision 6 自测记录

执行时间：2026-07-17T03:03:32Z

环境：macOS 26.5.1、Google Chrome 150.0.7871.116、Git 2.50.1

## 1. 可复现命令

在仓库根目录执行：

```sh
runs/WI-002/product-ui-designer/supporting-files/scripts/render-boards.sh
runs/WI-002/product-ui-designer/supporting-files/scripts/validate-delivery.sh
git diff --check
```

渲染脚本默认使用本机 Chrome；可通过 `CHROME=/path/to/chrome` 指定其他可执行文件。HTML 使用仓库内相对路径引用 11 张正式 UI 输入，必须在完整仓库目录结构中渲染。

## 2. 自动检查结果

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 必需交付文件存在且非空 | PASS | 验证脚本逐项检查 `answer.md`、规格、清单、HTML 和 PNG |
| 11 张输入映射 | PASS | `input-mapping.md` 中 5 张用户端 + 6 张管理端路径全部命中 |
| 核心规则覆盖 | PASS | 375–430、软键盘、安全区、生成/停止/重试、管理员页面、20 条分页、System Prompt 规则全部命中 |
| H5 PNG | PASS | 1680 × 3200、RGB、非隔行 PNG |
| 管理端 PNG | PASS | 1800 × 5900、RGB、非隔行 PNG |
| HTML 基础内容 | PASS | 两板均有 doctype、PRD 标注、正式输入与最终补稿区域 |
| API Key 假值 | PASS | 管理板源码使用完整 `EXAMPLE_NOT_A_REAL_OPENAI_API_KEY_000000` |
| 凭据模式扫描 | PASS | 未命中私钥头、AWS Key、GitHub Token 或常见 OpenAI Key 模式 |
| Shell 语法 | PASS | 两个脚本均通过 `sh -n` |

`validate-delivery.sh` 最终输出：

```text
PASS png: h5-visual-board.png 1680x3200
PASS png: admin-visual-board.png 1800x5900
PASS 11 inputs mapped
PASS required state/rule coverage
PASS credential pattern scan
PASS delivery validation
```

## 3. 人工视觉检查

已用原始分辨率查看两张 PNG，并核对 HTML 渲染结果：

- H5：5 张正式稿完整显示；注册、空态、流式、停止、失败、重试、抽屉锁定、键盘、安全区、加载、搜索空态、发送失败与断网补稿均未横向溢出或裁切。
- H5 最终补稿输入区仅保留文本与发送/停止；正式输入缩略图中的“+”和图片图标已用黄色 PRD 差异说明标出，不作为最终实现。
- 管理端：6 张正式稿完整显示；登录、配置、列表、聊天详情、调用详情和通用状态矩阵均在画布内。
- 配置正式稿缩略图的疑似真实格式示例在渲染时被白色覆盖层替换为完整明文假值；最终补稿同样只使用该假值。
- 列表最终补稿明确为“每页 20 条”；正式稿的 10 条/页仅留作输入映射证据并有黄色差异说明。
- 调用详情最终补稿只显示实际 user/assistant 角色；无虚构 system 行，失败卡保留实际错误与部分返回。
- 字号层级、绿色强调、浅灰画布、白卡、侧栏、圆角、边框、表格和步骤轴与正式稿方向一致。

## 4. 内容一致性检查

- `ux-ui-spec.md` 的页面、状态、迁移和响应式规则与两张视觉板一致。
- `copy-catalog.md` 的按钮、错误、空态、状态、Toast 和恢复动作均可在规格或视觉板找到使用场景。
- `input-mapping.md` 与 `design-decisions.md` 对同一冲突给出一致结论：纯文本、20 条分页、API Key 明文假值、System Prompt 条件渲染、排除范围外动作。
- HTML 是 PNG 的唯一渲染源，PNG 由 `render-boards.sh` 重新生成；没有手工后期修改 PNG。

## 5. 已知限制

- “正式稿基准”区域忠实展示原始输入，因此会看见被判定为 PRD 冲突的稿件元素；这些元素均有差异标注，最终实现以同板“最终实现补稿”和 `ux-ui-spec.md` 为准。
- 视觉板是静态验收材料，不执行真实键盘、抽屉、流式或复制事件；完整事件时序和焦点规则由规格定义。
- HTML 依赖仓库内 `页面UI稿` 相对路径；PNG 为无需依赖输入文件的独立检查结果。

---
name: coordinate-agents-with-local-files
description: "使用同一台电脑上的共享本地目录协调多个一级 Codex Agent 完成一个 Mission，覆盖 Mission、Work Item、一级 Agent、Run、不可变 Message、定向任务通知、Polling 与 Artifact 的创建、执行、审核和验收。仅当用户明确指定 coordinate-agents-with-local-files Skill，或明确要求多个本机 Agent 通过同一个本地文件夹协作并在必要时唤醒相关 Codex 任务时使用。不要仅因用户提到本地文件、Agent、协作、Git 或软件开发而触发。"
---

# 使用本地文件协调多个 Agent

把用户指定的共享本地目录视为一个 Mission 的权威协作空间。正式事实只存在于协议文件中；Codex 任务通知只负责提醒，Polling 负责兜底。Git 可以归档，但不能作为通信前提。

创建、读取或修改正式协议文件前，完整读取 references/file-protocol.md。需要登记任务、发送定向提醒、处理通知失败或切换任务时，完整读取 references/thread-notifications.md。

## 遵守启用边界

- 只在用户明确调用本 Skill，或明确选择共享本地目录作为多 Agent 协作介质时启用。
- 不要因为项目位于 Git 仓库就切换为 Git 通信。
- 不要因安装本 Skill 自动迁移正在运行的 Mission、修改其文件或通知现有 Agent。
- 正在使用其他协调协议时，必须先获得 Mission Owner 或人工明确确认，再执行切换。

## 遵守核心约束

- 只让人工已经启动的一级 Agent 进入协议；不要自动发现、自动启动或自行登记其他任务。
- 从启动指令获取当前 agent_id 和共享目录绝对路径。缺少任一项时先请求人工提供，不要根据系统账号、Git 账号或任务标题推断。
- 确认所有一级 Agent 在同一台主机上访问同一个共享目录；不能确认时不要启用本地文件协议。
- 把 Mission Owner、Coordinator 和执行者都视为一级 Agent；不要再建立 Role 层。
- 不登记 Sub-agent，不让 Sub-agent Polling、收发正式 Message、读取本地任务映射或直接操作共享协议文件。由父 Agent 汇总并负责。
- 不建立数据库、锁服务、消息队列、Event、Governance、Candidate 或统一 Lifecycle 模块。
- 接受至少一次投递语义；使用唯一 ID、稳定幂等键、单路径写入权和本地 Checkpoint 消除重复动作。
- 每类当前状态只保存在一个权威位置。Message 只引用 Subject，不复制完整对象。
- 不把 task/thread ID 当作 Agent 身份、协议状态或 Message 送达证明。

## 使用固定目录

共享目录根：

    /
    ├── MISSION.md
    ├── WORKFLOW.yaml
    ├── items/
    ├── agents/
    ├── runs/
    ├── messages/
    ├── artifacts/
    └── .coordination-local/

前七项是正式共享状态。.coordination-local/ 是本机运行状态，只保存任务映射、Polling Checkpoint、去重记录、临时出站文件和通知日志；不得提交到 Git 或转为 Artifact。

如果项目启用 Git 归档，先确认 .coordination-local/ 已被忽略。没有权限修改忽略规则时，停止归档，不要冒险提交本机状态。

## 按职责行动

### Mission Owner

- 提出、启动、验收、拒绝、取消或重新打开 Mission。
- 只在人工明确确认后修改目标、范围、约束、必需交付物或验收标准。
- 不替代 Coordinator 拆解、分派或审核 Work Item。

### Coordinator

- 根据 Mission 创建、调整、分派和结束 Work Items。
- 登记一级 Agent，检查能力覆盖，处理阻塞、冲突和重新分配。
- 审核 Run；只把通过审核的内容复制为 Artifact。
- 所有必需 Work Items 完成后请求 Mission Owner 验收。
- 维护 .coordination-local/threads.yaml，或在用户负责映射时校验其可用性。
- 不直接执行 Work Item，不创建自己的 Run，不生产交付物。

### 其他一级 Agent

- 只执行分配给自己或自己合法认领的 Work Item。
- 在自己的 Run 中报告状态并承载待审核回答。
- 需要新增 Work Item、Agent、决策、协助或协议调整时发送 Request，不修改他人权威文件。
- 对自己创建的 Sub-agent、Run、Message 和交付质量负责。

## 保证并发安全

使用“单路径单写入者”，不使用全局文件锁：

- Mission Owner 管 Mission 内容。
- Coordinator 管 Workflow、Agents、Items 和 Artifacts。
- 每个一级 Agent 只管理自己的 Run。
- 任一一级 Agent只能新增 sender_agent_id 为自己的 Message 文件。
- Coordinator 管正式目录外的任务映射；各一级 Agent 管自己的 Checkpoint 和去重状态。

发布文件时遵守以下顺序：

1. 在 .coordination-local/ 下同一文件系统的临时路径写出完整新内容。
2. 校验格式、身份、revision、引用和写入权限。
3. 将完整文件原子重命名到正式路径；目标已存在时停止，不覆盖。
4. 重新读取正式文件确认发布结果。
5. 需要其他 Agent 关注时，发布成功后再发送任务通知。

更新已有权威文件时同样先写完整替代版本并校验，再原子替换。若当前工具不能保证原子替换，依靠单写入者缩小风险，并在修改后立即重读校验；不要让两个 Agent 同时编辑同一路径。

多个执行者需要修改产品源代码时，优先把工作保存在各自 runs/<WI>/<agent_id>/supporting-files/ 中。由通过验收的 Artifact 或专门的集成 Work Item 合并到产品目录。只有 Work Item 明确分割了互不重叠的路径，才允许并行直接写产品目录。

## 管理 Mission、Item、Agent 与 Run

按 references/file-protocol.md 的字段、状态与 revision 规则执行。

- Mission 只使用 draft、active、awaiting_acceptance、completed、cancelled。
- Work Item 只支持 depends_on 的 AND 启动依赖。
- Coordinator 是 Item 的唯一管理者；执行 Agent 不得把 Item 标为 completed。
- 同一 Work Item 可有多个一级 Agent Run；同一 Agent 对同一 Item 只有一个 Run。
- Run 使用 active、blocked、in_review、completed、failed、cancelled。
- Run 提交审核后冻结；被拒后恢复同一个 Run，不另建“修订 Run”。
- 活动 Run 超过 30 分钟且有实质进展时，至少更新一次快照。

前后端或其他跨 Item 合同需要协商时，把初始合同放入负责合同的 Work Item/Artifact。双方通过 question_asked、question_answered 或 work_item_proposed Message 提议变更；由合同所有者更新权威合同并递增 revision。依赖方重新读取新 Artifact 后再继续，不在聊天通知中维护合同副本。

## 使用不可变 Message

每个 messages/<message_id>.yaml 表示一条不可变 Message，只允许 request、notification、response。

发送时：

- 只在需要其他一级 Agent 知道、判断或行动时创建 Message。
- 使用唯一 message_id、稳定 idempotency_key 和最小 payload。
- recipient_agent_ids 只使用具体一级 Agent ID，或单独使用 @all。
- Subject 引用权威对象及其 revision，不复制完整对象或大型正文。
- 状态已变化时，先更新权威文件，再发送 Notification。
- Response 必须通过 in_reply_to 引用 Request。
- 发布后不修改或删除；错误通过 message_corrected 新 Message 纠正。

接收时：

- 校验 Schema、Mission、协调 epoch、发送者、接收者、Subject 和 revision。
- 用 message_id 去重读取，用 idempotency_key 去重业务动作。
- 重新读取 Subject 指向的权威文件，不仅根据 summary 或任务通知行动。
- 对有效 Request 发送明确 Response；“已读”不等于“已处理”。
- 无效、过期或无权限处理时不执行，回复拒绝、阻塞或补充信息请求。

## 定向唤醒相关任务

先发布 Message，再按 references/thread-notifications.md 判断是否需要提醒。

默认需要立即提醒：

- 直接 Request；
- 对未完成 Request 的 Response；
- Artifact 审核请求或审核结果；
- Mission 变更、验收、取消；
- 阻塞、解除阻塞、重新分配；
- 紧急配置冲突或需要人工决策的事项。

普通状态 Notification、常规进度和无行动要求的广播不立即提醒，交给 Polling。

提醒内容只包含 Mission 简称、message_id、相对路径和“重新读取 Subject”的指令，不粘贴完整 payload。把提醒发送到 threads.yaml 中该 agent_id 对应的 Codex 任务。@all 仅通知 active 一级 Agent，排除发送者，并尽量批量合并多个待处理 message_id。

任务提醒是尽力而为：

- 发送失败、任务不存在、任务未加载或映射过期时，保留已发布 Message。
- 记录本地失败并依赖 Polling；需要时请求人工刷新映射。
- 不因任务工具返回成功就把 Request 标为完成。
- 没有可用任务工具时继续使用纯本地文件和 Polling，不改变协议语义。

## 执行本地 Polling

只在人工启动一级 Agent 后运行 Polling。默认每 600 秒一轮，允许 WORKFLOW.yaml 覆盖；不要在每轮运行 git pull、fetch、commit 或 push。

每轮：

1. 读取 WORKFLOW.yaml，确认 transport 为 local_files、epoch 未变化且 Mission 仍允许行动。
2. 从本地 Checkpoint 前 lookback_seconds 开始扫描 messages/。
3. 找出发给当前 Agent、发给 @all、以及回应当前 Agent 未完成 Request 的 Message。
4. 校验、去重、重新读取 Subject，并按优先级处理。
5. 读取当前 Agent、相关 Items、自己的 Runs 和必要的同 Item Runs。
6. 执行有权限的动作，创建必要的 Response 或 Notification。
7. 重新校验写入结果。
8. 只有在 Message 已处理或已安全记录为待处理后推进 Checkpoint。

优先处理 Mission 取消或人工确认、直接 Request、未完成 Request 的 Response、审核、重新分配或解除阻塞、普通 Notification、广播和常规对账。

每 30 分钟重新读取 Mission、Workflow、当前 Agent、相关 Items、同 Item Runs 和未完成 Requests。Checkpoint 缺失、损坏、epoch 变化或任务迁移时执行 Bootstrap：扫描所有发给当前 Agent且没有有效 Response 的 Request，核对当前 Items、Runs 和 Mission 状态，再建立新 Checkpoint。

## 审核并生成 Artifact

- 执行 Agent 在 Run 中准备 answer.md 和可选 supporting-files/，将 Run 设为 in_review，再发送 artifact_review_requested。
- Coordinator 对照 Item、验收标准、主回答、附属材料和必要测试审核。
- 拒绝时发送具体原因，不创建 Artifact；让 Agent 修改同一 Run 后重提。
- 接受时把 answer.md 和 supporting-files/ 复制到 artifacts/<WI>/<agent_id>/，把 Run 设为 completed，并在 Item 中登记 accepted_artifacts。
- 至少一个 Artifact 被接受后把 Item 设为 completed，取消其他未完成 Runs但保留内容。
- 下游 Agent 和 Mission Owner 只消费 artifacts/，不把未审核 Run 当正式输入。

## 完成 Mission

- Coordinator 确认必需 Items、Artifacts 和未完成 Requests 后，将 Mission 设为 awaiting_acceptance 并请求验收。
- Mission Owner 拒绝时说明缺口，Coordinator 据此调整 Items。
- Mission Owner 接受时将 Mission 设为 completed；停止认领新工作，仅做必要清理。

## 在协议之间切换

不要让一个 Mission 同时把 Git 拉取和共享本地目录都当作消息传输。切换前：

1. 获得 Mission Owner 或人工明确确认，暂停所有一级 Agent 在安全检查点。
2. 对旧传输做最后一次同步或归档，确认没有只存在于其他副本的未发布 Run 或 Message。
3. 备份正式协议文件，升级所有可变正式对象到本 Skill 的 schema_version，并更新 WORKFLOW.yaml 的 transport 与 epoch。
4. 不改写旧协议下已经发布的不可变 Message；在 WORKFLOW.yaml 记录其 Git 基线为只读历史。仍未完成的旧 Request 由 Coordinator 用当前 Schema 重新发布，并在 payload 中引用旧 message_id。
5. 建立本机任务映射和各 Agent 新 Checkpoint。
6. 用一条无副作用的测试 Message 验证本地落盘、定向通知和接收去重。
7. 人工通知所有一级 Agent 使用同一 Skill、目录、agent_id 和 epoch 后再恢复。

任何 Agent 发现 transport、schema_version 或 epoch 不一致时立即停止写入，发送 configuration_conflict（能安全发送时）并请求 Coordinator 处理。

## 可选 Git 归档

只有 WORKFLOW.yaml 明确启用 coordinator_only 归档时才使用 Git：

- 只让配置的单一发布者执行 add、commit、pull、merge 或 push。
- 其他 Agent 不操作共享工作树的 Git index，不通过 Git 等待或传递 Message。
- 发布者只在协议文件完整、无临时文件且没有并发写入时做检查点提交。
- Git 冲突不改变本地权威状态；先停止归档并解决，不阻塞本地 Message 处理。
- 不使用 Issue、PR、Projects、Actions、评论或 Webhook 代替协议。

## 保护安全与隐私

- 不在正式文件、.coordination-local/ 或任务提醒中保存 SSH 私钥、API Key、Token、服务器密码、Cookie 或其他凭据。
- 不提交 .coordination-local/、内部思考、原始提示、无关日志或个人敏感信息。
- task/thread ID 只保存在本机运行目录，不写入 WORKFLOW、Agent、Run、Message 或 Artifact。
- Message 文件永久保留；除非协议升级且 Mission Owner 明确同意，不归档、移动或删除。

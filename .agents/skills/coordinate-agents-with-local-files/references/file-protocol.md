# 本地文件协议

在创建、验证或修改共享文件时使用本参考。示例中的说明文字不要复制进实际 YAML。

## 目录

- 通用规则
- 固定结构
- MISSION.md
- WORKFLOW.yaml
- 一级 Agent
- Work Item
- Run
- Message
- Artifact
- 本机运行状态
- 写入权与原子发布

## 通用规则

- 使用 UTF-8、LF 和 UTC ISO 8601 时间，例如 2026-07-16T08:00:00Z。
- 使用 lowercase kebab-case Agent ID，例如 research-agent。
- Work Item ID 使用递增 WI-001 格式，只由 Coordinator 分配。
- Run ID 使用 RUN-<WI>-<agent_id>，例如 RUN-WI-001-research-agent。
- Message ID 使用 msg- 前缀的 ULID 或 UUID，文件名必须与 message_id 一致。
- 切换后新建或继续维护的正式对象使用 schema_version: "0.2"。唯一例外是 WORKFLOW.yaml 明确登记、且已存在于迁移基线 Git 提交中的旧版不可变 Message；它们只作只读历史，不能继续驱动业务动作。
- 对象发生实质变化时递增 revision；纯格式或拼写修改可以不递增。
- 所有路径引用使用共享目录根的相对路径，不把绝对本机路径写入正式对象。
- 正式事实存在于协议文件，不存在于 Codex 任务通知、Git 提交说明或口头消息中。
- 不使用 GitHub Issue、PR、评论、标签、Projects、Actions 或 Webhook 协作。

## 固定结构

    /
    ├── MISSION.md
    ├── WORKFLOW.yaml
    ├── items/
    │   └── WI-001.md
    ├── agents/
    │   └── research-agent.yaml
    ├── runs/
    │   └── WI-001/
    │       ├── research-agent/
    │       │   ├── RUN.yaml
    │       │   ├── answer.md
    │       │   └── supporting-files/
    │       └── analyst-agent/
    │           ├── RUN.yaml
    │           └── answer.md
    ├── messages/
    │   └── msg-01JABC.yaml
    ├── artifacts/
    │   └── WI-001/
    │       └── research-agent/
    │           ├── answer.md
    │           └── supporting-files/
    └── .coordination-local/
        ├── threads.yaml
        ├── checkpoints/
        ├── dedupe/
        ├── outbox/
        └── notification-log/

MISSION.md、WORKFLOW.yaml、items/、agents/、runs/、messages/ 和 artifacts/ 是正式共享协议。

.coordination-local/ 只用于同一主机上的运行元数据，必须被 Git 忽略，不得复制进 Artifact。不存在时由 Coordinator 创建最小目录；不要为了整齐预先创建空日志。

## MISSION.md

保存任务语义：

    # Mission

    ## 目标

    说明最终要实现的结果。

    ## 范围

    说明包含和不包含的工作。

    ## 任务约束

    列出时间、资源、合规和方法限制。

    ## 必需交付物

    列出 Mission 结束前必须存在的成果。

    ## 验收标准

    列出 Mission Owner 判断完成的可检查条件。

目标、范围、任务约束、必需交付物和验收标准属于 Mission 内容，修改前必须获得 Mission Owner 或人工明确确认。第一版信任确认 Message，不要求签名证明。

## WORKFLOW.yaml

    schema_version: "0.2"
    mission_id: mission-001
    mission_revision: 1
    status: active

    mission_owner: mission-owner
    coordinator: coordinator

    coordination:
      transport: local_files
      epoch: 1
      direct_notifications: codex_tasks
      legacy_message_history:
        mode: read_only
        schema_version: "0.1"
        baseline_git_commit: "0123456789abcdef0123456789abcdef01234567"
        cutover_at: "2026-07-16T08:00:00Z"
      git_archival:
        mode: none
        publisher_agent_id: null

    polling:
      interval_seconds: 600
      lookback_seconds: 300
      reconciliation_minutes: 30

    created_at: "2026-07-16T08:00:00Z"
    updated_at: "2026-07-16T08:00:00Z"

允许的 Mission status：

    draft
    active
    awaiting_acceptance
    completed
    cancelled

允许的 coordination.transport 只有 local_files。任何 Agent 读取到其他值时停止按本 Skill 写入。

coordination.epoch 是正整数。首次启用为 1；每次协调传输迁移、正式目录恢复到旧快照或需要使旧 Checkpoint 失效时递增。Message 必须携带创建时的 epoch。

direct_notifications 允许：

    codex_tasks
    none

从 Git 文件协议切换时必须增加 legacy_message_history；新建 Mission 可以省略。字段含义：

- mode 只能是 read_only。
- schema_version 是迁移前 Message 的 Schema。
- baseline_git_commit 是切换前最后一次完整同步的 40 位 Git commit。
- cutover_at 是切换决定生效的 UTC 时间。

只有同时满足以下条件的旧 Message 才能作为合法历史读取：

- 文件已存在于 baseline_git_commit；
- schema_version 等于登记值；
- 文件未在切换后被修改。

旧 Message 不参与新 epoch 的普通 Polling。仍未完成的旧 Request 由 Coordinator 重新发布为 schema_version 0.2 的新 Request，并在 payload.supersedes_legacy_message_id 引用旧 message_id；旧文件保持不变。

git_archival.mode 允许：

    none
    coordinator_only

mode 为 none 时 publisher_agent_id 必须为 null。mode 为 coordinator_only 时 publisher_agent_id 必须引用一个 active 一级 Agent，通常是 coordinator；只有该 Agent 可以操作共享工作树的 Git index 和远端。

mission_owner 和 coordinator 必须引用 agents/ 中两个不同的一级 Agent。

## 一级 Agent

路径：agents/<agent_id>.yaml。

    schema_version: "0.2"
    agent_id: research-agent
    agent_type: worker
    status: active

    responsibilities:
      - 市场研究
      - 信息来源验证

    capabilities:
      - web-research
      - data-analysis

    created_at: "2026-07-16T08:00:00Z"
    updated_at: "2026-07-16T08:00:00Z"

agent_type 允许：

    mission_owner
    coordinator
    worker

status 允许：

    active
    paused
    retired

只登记人工启动的一级 Agent。不要写入 Sub-agent、task/thread ID、绝对路径、Checkpoint、当前 Item 列表或凭据。

## Work Item

路径：items/<work_item_id>.md。YAML Frontmatter 保存控制字段，正文保存任务语义。

    ---
    schema_version: "0.2"
    work_item_id: WI-001
    revision: 1
    mission_revision: 1
    status: ready
    depends_on: []
    accepted_artifacts: []
    created_by: coordinator
    created_at: "2026-07-16T08:00:00Z"
    updated_at: "2026-07-16T08:00:00Z"
    ---

    # 验证目标市场规模

    ## 任务说明

    验证主要来源的市场规模数据，并解释差异。

    ## 必需交付

    - 一份结论明确的主回答；
    - 必要的数据和来源材料。

    ## 验收标准

    - 至少使用三个独立来源；
    - 解释不同来源之间的数据差异。

status 允许：

    waiting
    ready
    in_progress
    in_review
    completed
    cancelled

depends_on 只包含 Work Item ID。空数组表示没有启动依赖；非空时所有引用项必须为 completed。只支持 AND 启动依赖，不支持 OR、完成依赖或表达式。

聚合多个 Runs 时：

- 没有 Run 且依赖满足时使用 ready。
- 至少一个 Run 为 active、blocked 或 failed，且没有 Run 等待审核时使用 in_progress。
- 至少一个 Run 为 in_review，且尚无 Artifact 被接受时使用 in_review。
- accepted_artifacts 非空时使用 completed，并取消其他未完成 Runs。

不保存唯一 responsible_agent。Coordinator 通过 Message 分派；active 一级 Agent也可合法认领 ready 或 in_progress Item。runs/<work_item_id>/<agent_id>/ 是实际参与记录。

accepted_artifacts 保存 Coordinator 接受的 Artifact 目录相对路径。数组至少包含一个有效路径时，Item 才能为 completed。

## Run

路径：runs/<work_item_id>/<agent_id>/RUN.yaml。

    schema_version: "0.2"
    run_id: RUN-WI-001-research-agent
    work_item_id: WI-001
    work_item_revision: 1
    agent_id: research-agent
    status: active

    started_at: "2026-07-16T08:00:00Z"
    updated_at: "2026-07-16T09:00:00Z"

    progress_summary: 已完成主要数据源收集
    next_step: 验证来源差异并完善主回答
    blocker: null

status 允许：

    active
    blocked
    in_review
    completed
    failed
    cancelled

blocked 时 blocker 为对象：

    blocker:
      reason: 缺少内部销售数据访问权限
      needs_action_from:
        - coordinator
      requested_action: 提供数据或确认替代来源

同一目录必须包含 answer.md。没有附属材料时可以省略 supporting-files/。同一 Work Item 可包含多个一级 Agent Run，但同一 agent_id 只使用一个目录；审核拒绝后继续修改该 Run。

Run 达到 completed、failed 或 cancelled 后保留目录和最终内容，不删除。

## Message

路径：messages/<message_id>.yaml。Message 不可变，文件名必须与 message_id 一致。

    schema_version: "0.2"
    message_id: msg-01JABC
    mission_id: mission-001
    coordination_epoch: 1
    intent: request
    message_type: artifact_review_requested

    sender_agent_id: research-agent
    recipient_agent_ids:
      - coordinator

    subject:
      type: work_item
      id: WI-001
      revision: 1

    summary: 请求审核 WI-001 的当前回答
    created_at: "2026-07-16T10:00:00Z"
    idempotency_key: artifact-review/WI-001/RUN-WI-001-research-agent/attempt-1

    payload:
      run_id: RUN-WI-001-research-agent
      run_path: runs/WI-001/research-agent

intent 允许：

    request
    notification
    response

Response 必须增加：

    in_reply_to: msg-01JABC

Subject type 允许：

    mission
    work_item
    agent
    run
    artifact
    message

message_type 第一版允许：

    work_item_proposed
    work_item_proposal_reviewed
    work_item_assignment_requested
    work_item_claimed
    work_item_assigned
    work_item_state_changed
    agent_requested
    agent_request_reviewed
    agent_registered
    agent_state_changed
    run_started
    run_blocked
    run_resumed
    run_failed
    run_cancelled
    artifact_review_requested
    artifact_reviewed
    artifact_accepted
    question_asked
    question_answered
    mission_change_confirmation_requested
    mission_change_confirmed
    mission_change_rejected
    mission_acceptance_requested
    mission_acceptance_accepted
    mission_acceptance_rejected
    mission_state_changed
    message_corrected
    configuration_conflict

表达提议、请求或问题时使用 request；表达已发生事实时使用 notification；表达审核、回答、接受或拒绝时使用 response。

recipient_agent_ids 使用一个或多个具体 agent_id，或只使用 @all；不能混用。发送者是否排除在 @all 之外由接收扫描规则处理。

payload 只保存处理 Message 所需的最小结构化信息。不要放入完整对象、大型正文、task/thread ID、绝对本机路径、密码、Token 或内部思考。

读取当前协议 Message 时确认 schema_version 为 0.2，且 coordination_epoch 等于 WORKFLOW 当前 epoch。

读取登记的旧版历史 Message 时只允许审计和判断是否需要迁移：

- 不补写 coordination_epoch，不修改 intent、payload 或其他字段；
- 不直接执行业务动作，也不在旧 Schema 下响应；
- 若它代表未完成 Request，交给 Coordinator 创建当前 Schema 的替代 Request；
- 不符合 WORKFLOW 中 legacy_message_history 基线的旧版文件视为 configuration_conflict。

Message 文件第一版永久保留，不归档、移动、覆盖或删除。发现错误时新增 message_corrected 并引用原 Message。

## Artifact

路径：artifacts/<work_item_id>/<agent_id>/。

    artifacts/WI-001/research-agent/
    ├── answer.md
    └── supporting-files/
        ├── data.csv
        └── sources.md

answer.md 是必需主回答；即使主要交付是代码、数据或演示文稿，也用它说明索引、结论和验证情况。supporting-files/ 可选。

只有 Coordinator 审核通过后才创建 Artifact。复制 Run 的 answer.md 和 supporting-files/，不要复制 RUN.yaml，不删除原 Run，不创建 artifact.yaml、失败目录、版本目录或 Registry。

completed Item 必须至少存在一个 artifacts/<work_item_id>/<agent_id>/answer.md，并在 accepted_artifacts 中引用。允许接受多个一级 Agent 回答。

## 本机运行状态

.coordination-local/ 不是正式协议，不要求跨主机可移植。

- threads.yaml：Coordinator 管理的 agent_id 到 Codex task/thread 的映射。
- checkpoints/<agent_id>.yaml：该 Agent 最近安全处理位置、最后对账时间和 epoch。
- dedupe/<agent_id>：该 Agent 已处理 message_id 和 idempotency_key 的本地集合。
- outbox/：原子发布前的完整临时文件；发布后清理。
- notification-log/：尽力而为的通知结果；不能作为送达证明。

Checkpoint 示例：

    schema_version: "0.2"
    mission_id: mission-001
    coordination_epoch: 1
    agent_id: research-agent
    last_scan_at: "2026-07-16T10:00:00Z"
    last_reconciliation_at: "2026-07-16T09:30:00Z"

不要把内部思考、原始 Prompt、凭据、业务答案或 Message 正文存入本机运行状态。

## 写入权与原子发布

| 路径 | 写入者 |
|---|---|
| MISSION.md | Mission Owner；Mission 内容修改需人工确认 |
| WORKFLOW.yaml | Mission Owner 管授权状态；Coordinator 管协调配置和验收请求状态 |
| items/ | Coordinator |
| agents/ | Coordinator |
| runs/<WI>/<agent_id>/ | 对应 agent_id 的一级 Agent |
| messages/<message_id>.yaml | sender_agent_id 对应的一级 Agent，只能新增 |
| artifacts/<WI>/<agent_id>/ | Coordinator 审核通过后创建 |
| .coordination-local/threads.yaml | Coordinator或用户 |
| .coordination-local/checkpoints/<agent_id>.yaml | 对应 agent_id |
| .coordination-local/dedupe/<agent_id> | 对应 agent_id |

原子发布新文件：

1. 在 .coordination-local/outbox/ 写完整临时文件。
2. 校验 Schema、权限、引用、revision、epoch、文件名和内容。
3. 在同一文件系统内原子重命名到目标；目标已存在时停止。
4. 重读正式目标并确认。

替换已有状态文件：

1. 重新读取当前权威版本，确认 revision 没有变化。
2. 生成完整下一版本到临时文件。
3. 校验下一版本和调用者权限。
4. 原子替换并重读。

不要使用“先清空再写入”、多 Agent 共享临时文件或覆盖已存在的 Message。不能安全判定语义冲突时停止相关写入，尽可能创建 configuration_conflict Request，并等待 Coordinator。

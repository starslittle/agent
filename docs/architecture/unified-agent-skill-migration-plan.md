# 启点统一助手、Skill 与个人 Wiki 迁移实施方案

> 版本：v0.1
>
> 状态：实施方案草案；冻结基准提交后按 Task 执行
>
> 最后更新：2026-07-30

## 0. 文档目的

本文把产品目标、上一轮 Agent Runtime 迁移 TODO、当前代码事实和下一轮实施顺序
连接成一份可执行方案。

- 产品范围以 [`秋招最小 MVP`](../product/recruiting-mvp.md) 为当前优先级；
- 产品终局参考 [`Web MVP`](../product/web-mvp.md) 和
  [`完整产品蓝图`](../product/future-product.md)；
- 目标结构由 [`统一助手与 Skill 目标架构`](unified-agent-skill-architecture.md)
  定义；
- Runtime 可靠性继续遵守 [`Agent Runtime 目标架构`](agent-runtime.md)；
- 历史完成项和遗留项以
  [`Agent Runtime 迁移状态`](agent-runtime-migration-progress.md) 为依据；
- Create/Attach/Cancel、结构化事件和故障验收细节参考
  [`Agent Runtime P0 稳定化方案`](agent-runtime-p0-stabilization-plan.md)。

本文定义实施顺序，不复制上述文档的全部内容。发生冲突时，按 `AGENTS.md` 的事实
优先级处理。

## 1. 当前起点

### 1.1 上一轮 Runtime 迁移已经完成的部分

当前 `main` 已经具备：

```text
Go Product Control Plane
→ Python Agent Runtime
→ 唯一 AgentApplication
→ 唯一 Compiled Root Graph
→ chat_v1 / research_v1 / fortune_v1
→ Model Gateway / Capability Registry
```

代码事实：

- Go 拥有认证、会话、消息和 Product Run；
- Python 拥有 LangGraph、Workflow、模型和 Capability 执行；
- Chat、Research、Fortune 已经是同一 Root Graph 下的受控 Subgraph；
- Legacy 与 V1 复用同一 Python 执行架构；
- 旧 Graph、旧节点、重复 Provider 和旧 RAG 路径已经清理；
- Runtime Event、Artifact、Checkpoint、Lease 和 Redis 协调能力已经建立；
- 显式取消的页面、Product Run、Python execution 和消息终态一致性已经修复。

因此下一轮迁移不能重新建设第二个 Root Graph、Runtime、Model Gateway 或 Tool
Executor，也不重写现有 Research/Fortune Workflow。

### 1.2 尚未完成的 Runtime 产品协议

当前仍存在：

- 浏览器通过 `POST /messages/stream` 同时创建 Run 和订阅 SSE；
- 前端需要等待 SSE `meta` 才能获得 `run_id`；
- `progress` 和 `tool.completed` 仍被投影为普通 `delta`；
- 前端仍可能把运行活动与最终回答累积到同一 Markdown；
- Research Citation 尚未作为结构化浏览器数据展示；
- 生产 Compose 仍默认 `legacy + memory + none`；
- P0 故障、一致性、权限和脱敏验收尚未形成最终统一报告。

准确状态是：

```text
Runtime 代码架构迁移已经完成
≠ Runtime 产品协议已经全部完成
≠ V1 已获得生产默认切换授权
```

### 1.3 新产品迁移尚未进入运行代码

当前仍然：

- 前端用“深度思考”布尔值选择 `research_agent`；
- Go、Python 请求和业务数据仍传播 `agent_name`；
- Python 没有 Skill Manifest/Registry；
- Run 没有 `requested_skill/resolved_skills`；
- 没有稳定的产品 `model_id`；
- 没有 Wiki、Markdown、Proposal、Decision 产品表；
- 没有 `/decision`、`/fortune` 和 Skill Chip；
- 没有 Wiki 页面和 Agent Runs 页面；
- 没有 Memory Proposal 用户确认闭环。

第一项 Skill 基础任务已经写成
[`TASK-001`](../../collaboration/tasks/TASK-001-skill-contract.md)，但在形成 Git
基准提交前保持 `draft`。

## 2. 实施原则

### 2.1 先稳定依赖，再增加产品对象

实施依赖为：

```text
Product Run 与浏览器事件
→ Skill 契约
→ Skill Run 跨服务协议
→ Root Assistant
→ 统一助手前端
→ Wiki 与个人上下文
→ Decision 与 Proposal
→ 完整产品闭环
```

纯定义、无运行行为变化的 Skill Manifest/Registry 技术上可以在 Runtime Phase 0
收口期间实施，但默认不跨 ROUND-01 提前执行；只有用户显式调整轮次授权时才可并行。
Skill 接入请求链仍必须等待 Product Run 和浏览器事件稳定。

### 2.2 以纵向产品链路验收

不以新增目录、类或页面数量判断完成。每个里程碑必须形成可观察行为，最终以秋招
MVP 唯一验收链路为准。

### 2.3 兼容迁移，不做 Big Bang

- 旧 `agent_name` 和旧消息流在兼容期继续可读；
- 新协议先并存、通过自动测试和 Codex E2E 后再切前端；
- 新前端不继续产生即将废弃的产品语义；
- 兼容 Adapter 有明确删除条件；
- 数据 Migration 向前兼容，不重写已有用户数据。

### 2.4 自动验证与独立产品验收分层

- Grok 负责静态检查、单元测试、模块级集成测试和故障注入脚本；
- Codex 负责代码与架构审查，以及 Browser / Computer Use 产品级 E2E；
- 自动测试通过不等于产品 E2E 通过；
- 生产切换需要用户单独授权。

### 2.5 按业务轮次交付

28 个 Task 不作为一次长程执行。实施按五个业务轮次推进：

```text
可信运行链路
→ 统一 Agent、Skill 与观测
→ 个人 Wiki、Markdown 与确认写入
→ Decision 秋招 MVP
→ Review 复盘
```

每轮形成独立用户结果、完整 E2E、上轮回归、能力关闭和重新启用演练，以及稳定
accepted commit。用户一次只授权一轮；本轮完成后必须停止，不自动进入下一轮。

业务轮次可独立验收和暂停，但不是无依赖并行产品。上层可以单独关闭；关闭底层时必须
同时关闭依赖它的上层能力。

## 3. 普通链路与“深度思考”链路的结合

### 3.1 当前行为

```text
deep = false
→ default_llm_agent
→ chat_v1

deep = true
→ research_agent
→ research_v1
```

当前选择发生在前端，Python Root Graph 只把传入的 Agent 名称映射为 Workflow。
“深度思考”同时混合了模型推理能力和 Research 工作流两个不同概念。

### 3.2 目标结合点

结合点位于 Python Root Assistant / Skill Resolver：

```text
统一请求
→ 检查显式 requested_skill
→ 没有显式 Skill 时进行结构化路由
→ 权限、模型能力、输入完整性、风险和预算校验
→ Direct Answer 或最多一个主 Skill
```

执行分支：

```text
Root Assistant
├── Direct Answer
│   └── chat_v1
├── Research Skill
│   └── research_v1
├── Fortune Skill
│   └── fortune_v1
└── Decision Skill
    └── decision_v1
```

`chat_v1` 与 `research_v1` 不合并为一张自由执行的大图。它们共享 Root Assistant、
Product Run、Context Package、Model Gateway、Capability Registry、事件、Artifact
和 provenance。

### 3.3 模型推理与 Research 分离

- 模型是否支持或启用原生推理由 `model_id`、Model Catalog 和服务端 Profile 决定；
- 是否需要联网检索、多来源比较和证据评估由 Skill Resolver 决定；
- 产品不展示模型隐藏思维过程；
- Research 的计划、工具和证据作为结构化 Activity/Citation 展示；
- 前端删除永久“深度思考”Agent 模式。

第一版路由原则：

| 请求 | 目标 |
|---|---|
| 简单问答、改写、总结已有上下文 | Direct Answer / `chat_v1` |
| 最新外部信息、多来源比较、证据评估 | Research / `research_v1` |
| 显式 `/research` | Research / `research_v1` |
| 中低置信度 Research | 直接回答或询问是否调研 |
| 自动识别 Fortune | 先向用户确认，不静默执行 |

## 4. 历史 TODO 追溯

| 历史 TODO | 当前判断 | 实施落点 |
|---|---|---|
| 显式取消终态一致 | 已完成 | 全程回归，不重新实现 |
| Activity 与正文分离 | 未完成 | M2 结构化浏览器事件 |
| Create/Attach/Cancel 分离 | 未完成 | M3 Product Run 生命周期 |
| Go Run Supervisor | 未完整落地 | M3 Product Run 生命周期 |
| P0 自动技术验收报告 | 部分测试已有 | M4 自动门禁与独立 E2E |
| Citation 结构化 | 未完成 | M5 Citation 投影与渲染 |
| Model Catalog 与稳定 `model_id` | 未完成 | M6 Skill Run 协议 |
| Skill Registry | 未开始 | M1 Skill 契约基础 |
| `requested_skill/resolved_skills` | 未开始 | M6 Skill Run 协议 |
| 单一助手模式 | 未开始 | M7 Root Assistant、M8 前端 |
| Research/Fortune Skill 化 | 未开始 | M7 Root Assistant |
| 废弃前端 Agent 模式 | 未开始 | M8 统一助手前端 |
| Skill Chip 与活动区 | 未开始 | M8 统一助手前端 |
| 模型选择器 | 未开始 | 稳定 `model_id` 后进入后续范围 |
| Research 自适应 0/1/N 检索 | 未开始 | P2，不阻塞秋招 MVP |
| Fortune 知识 Capability | 未开始 | P2，不阻塞基础 Fortune Skill |
| 记忆确认与遗忘 | 未开始 | M9/M10 Wiki 与 Proposal |
| 决策实验室和复盘 | 未开始 | M11 Decision 与闭环 |
| 写 Capability operation ledger | 未开始 | 出现外部副作用写能力前完成 |
| MCP、第三方 Skill 市场 | 未开始 | 当前明确不做 |
| 更大规模 Worker 与跨地域 | 未开始 | 当前明确不做 |

每个后续 Task 必须通过 `source_todos` 引用本表对应的原始文档章节。没有历史 TODO
来源的新产品需求也必须说明产品文档来源。

## 5. 迁移里程碑

本节编号描述技术能力，不代表跨业务轮次的执行授权顺序。实际执行顺序以
[`业务交付轮次`](../../collaboration/rounds/README.md) 为准。

### M0：冻结设计与执行基准

交付：

- 产品、架构、ADR 和协作协议形成 Git 基准提交；
- 修正文档中已实施、部分实施和未实施的状态；
- 用户授权 ROUND-01；
- ROUND-01 与 TASK-002 写入完整 `base_commit`，TASK-002 改为 `ready`；
- 从基准提交创建 TASK-002 的 Grok 独立 worktree。

门禁：

- 工作树中用户已有修改被明确纳入或排除；
- Task 引用路径存在；
- Task、Handoff、Review 模板可用；
- 没有业务代码行为变化。

### M1：Skill 契约基础

交付：

- Skill Manifest；
- Skill Registry；
- `skills.yaml` 只登记已有 Workflow 的 Research/Fortune；
- Workflow、Capability、模型要求和配置 fingerprint 启动校验。

限制：

- 不接入当前请求链；
- 不改 Go、前端、Workflow 和 Prompt；
- 不登记尚未实现的 Decision；
- 不建立第二套 Root Graph 或 Tool Registry。

对应当前 [`TASK-001`](../../collaboration/tasks/TASK-001-skill-contract.md)。

### M2：结构化浏览器事件

目标事件：

```text
meta
activity
answer_delta
citation
artifact
proposal
confirmation_required
done
error
```

核心不变量：

```text
assistant_message.content
==
按 sequence 拼接的全部 answer_delta
==
实时页面正文
==
刷新后的正文
==
默认复制内容
```

`progress`、Tool、Citation、Artifact 和 Proposal 不能进入最终回答正文。

门禁：

- Go/Python/浏览器事件具有契约测试；
- 老消息保持兼容；
- Codex 验证实时、刷新和复制结果一致；
- Tool/Progress 只出现在 Activity 区域。

### M3：Create / Attach / Cancel 与 Run Supervisor

目标 API：

```text
POST   /api/v1/conversations/{id}/runs
GET    /api/v1/agent-runs/{run_id}/events?starting_after=N
DELETE /api/v1/agent-runs/{run_id}
```

交付：

- 创建成功立即返回可寻址 `run_id`；
- Go Run Supervisor 独立于浏览器连接拥有执行生命周期；
- Attach/Re-attach 支持 `starting_after`；
- 浏览器断开只 detach；
- 显式取消才改变 Run 语义；
- Go 重启或传输恢复不重复最终消息。

门禁：

- 创建、订阅、重附着和取消分别有契约与集成测试；
- Codex 使用 Browser / Computer Use 验证刷新恢复、停止、竞态和后续会话解锁。

### M4：P0 自动门禁与独立 E2E

自动验收至少覆盖：

- Python 重启和 checkpoint 恢复；
- Go 或浏览器断开后的重新附着；
- 失败、超时和取消后的会话解锁；
- 事件 sequence 连续、重复幂等和缺口失败关闭；
- Product Run、Python execution 和 message 终态一致；
- Trace/provenance 完整且脱敏；
- 跨用户 Run、Event、Message 访问拒绝。

Grok 交付可重复执行的测试和摘要报告；Codex 独立执行真实产品 E2E 并决定是否
通过。未通过前不能把新协议作为唯一前端路径。

### M5：结构化 Citation

交付：

- Go 投影 `citation_id/title/url/snippet/source_type`；
- Citation 与 Run、Artifact、消息建立稳定关联；
- 前端渲染可点击角标和来源列表；
- 实时、刷新、复制和重新附着保持一致；
- 不用正则猜测任意方括号文本。

Research 对用户正式可见前必须完成本里程碑；它不阻塞 M1 的纯 Skill 定义。

### M6：Skill Run 跨服务协议

创建请求逐步迁移为：

```json
{
  "content": "下一轮面试应该优先准备什么？",
  "client_message_id": "uuid",
  "model_id": "auto",
  "requested_skill": "decision"
}
```

Run 冻结并记录：

- `model_id`；
- `requested_skill`；
- `resolved_skills`；
- `primary_skill`；
- `selection_source`；
- Skill/Workflow 版本；
- 模型与 Capability 快照；
- 后续使用的 Context Package ID。

兼容映射：

```text
default_llm_agent -> requested_skill = null
research_agent    -> requested_skill = research
fortune_agent     -> requested_skill = fortune
```

`agent_name` 只留在兼容 Adapter 和旧数据读取路径；新前端和新产品对象不继续扩散。
`model_id` 首轮只需要稳定支持 `auto`，模型选择器 UI 不进入当前门禁。

### M7：Root Assistant 与现有 Skill

交付：

- Root Skill Resolver；
- 显式 Skill、自动路由、置信度和确认策略；
- Research/Fortune Manifest 接入现有 Subworkflow；
- Direct Answer 保持非 Skill 路径；
- Skill 不得绕过模型和 Capability 校验；
- Skill、Workflow、Capability 和选择来源进入 Run provenance。

安全规则：

- 显式 Skill 优先但仍需校验；
- Fortune 自动识别后先确认；
- 一次 Run 最多选择一个主 Skill；Direct Answer 的 Skill 集合为空；
- 简单对话默认不联网、不调用工具；
- 不开放任意多 Skill 自由编排。

### M8：统一助手前端与 Agent Runs

进入门禁：

- ROUND-01 已完成 TASK-004～007、全量 E2E 和回滚演练并标记为 `accepted`；
- ROUND-02 已获得用户明确授权；
- Skill Run 协议、Root Resolver 与 Research/Fortune Skill 接入已经形成稳定前端契约；
- 奇点 AI 已按 ADR-012 形成远程设计归档 Tag。

交付：

- 将正式产品从奇点 AI 迁移为启点，统一品牌、favicon、metadata、Design Token、
  登录页、应用外壳、侧栏、对话空白页和消息视觉；
- 删除“深度思考”Agent 模式开关；
- 新前端不提交 `agent_name`；
- `/` 菜单只展示当前真实 available 的 Skill；ROUND-02 支持 `/fortune`，Decision
  只有在 ROUND-04 标记 available 后才自动出现；
- 展示实际 Skill 和选择来源；只有存在服务端公开的真实上下文摘要时才展示上下文
  数量，ROUND-02 不伪造个人信息；
- Activity、Citation、Artifact 与回答正文分层；
- Agent Runs 页面展示真实状态、步骤、模型、Skill、Capability、Token、耗时和错误。

Agent Runs 同时作为内部观测能力的唯一产品投影：普通用户只能查看自己的 Run，
`observability_admin` 通过独立只读路由查看跨用户脱敏 Run，并复用同一套查询模型和
前端组件。管理员视图补充用户、Skill、Workflow、Model、状态、错误码和时间筛选，
但不提供取消、重放、数据修改或生产控制能力。原始日志仍留在服务端，不新建第二套
观测服务。

不展示模型隐藏思维过程，不为 Research/Fortune 建立独立助手身份。

实施顺序固定为：先完成统一 Agent 与现有 Skill 的服务端协议，再由 TASK-012 一次完成
启点视觉基础和真实 Skill 交互，随后由 TASK-013/028 完成用户 Runs 与内部观测。
ROUND-01 不夹带品牌迁移，ROUND-03～04 只在已经验收的启点外壳上增加 Wiki、
Proposal 和 Decision。完整决策见
[`ADR-013`](../decisions/ADR-013-qidian-frontend-migration-sequence.md)。

### M9：Wiki Item 与 Context Package

第一版产品对象：

```text
WikiItem
WikiItemRevision
WikiItemSource
ContextUsage
```

最小信息类型：

```text
confirmed_fact
current_state
personal_rule
ai_analysis
```

最小状态：

```text
candidate
confirmed
rejected
outdated
forgotten
```

Go 负责按用户、状态、领域、时间和用途组装最小 Context Package。Python 只消费
Context Package，不直接查询或写入产品表。

个人 Context 接入后，同一 Product Run 先由 Python Resolver 使用最小 Routing
Context 产生 `SkillResolution/ContextRequirements`，再由 Go 组装并冻结
ContextPackage，最后由 Python 复用冻结结果执行。路由和执行不得复制两套 Resolver，
重试或重连不得改变已经冻结的结果。

首轮优先 PostgreSQL 过滤和简单全文检索，不因数据量很小而提前建设复杂向量系统。

### M10：Markdown 与 Wiki Update Proposal

流程：

```text
上传一篇 Markdown
→ 保存原文
→ Python 提取候选信息
→ Go 保存 Proposal
→ 用户接受、修改、暂缓或拒绝
→ Go 事务更新 Wiki 与历史版本
```

未确认、被拒绝、已过期或已遗忘的信息不能进入默认上下文。Python 不能直接提交
长期事实。

### M11：Decision 与唯一产品闭环

Decision Skill 使用事实、当前状态和个人规则，输出：

- 问题；
- 实际使用的个人上下文；
- 选项、收益、代价和反例；
- 未知项与重新评估条件；
- Decision Draft；
- 可选 Wiki Update Proposal。

最终验收链路：

```text
Wiki 保存求职状态
→ 导入面试复盘 Markdown
→ 确认候选信息
→ 询问下一轮准备方向
→ 自动选择 Decision Skill
→ 展示所用上下文
→ 流式返回分析
→ Agent Run 展示真实步骤
→ 产生薄弱点更新建议
→ 用户确认后更新 Wiki
→ 保存最终选择
→ 下一次对话使用更新信息
```

该链路通过，秋招 MVP 才成立。

### M12：发布与生产切换

代码完成不等于生产默认切换。生产切换必须单独满足：

- PostgreSQL 备份和恢复验证；
- Runtime Migration、Checkpoint Schema 和最小权限；
- Redis、Secret 和连接配置；
- `v1 + postgres + redis` 测试或小流量运行；
- 错误率、延迟、成本、取消和恢复观测；
- 用户明确授权。

生产操作遵守
[`Agent Runtime 上线与回滚`](../operations/agent-runtime-rollout.md)，不由执行 Task
自动完成。

## 6. Task 设计规则

### 6.1 一个 Task 一个可验收边界

后续编号在 Task 正式写入时冻结。除 TASK-001 外，不把本文的里程碑编号直接当作
最终 Task 编号；一个高风险里程碑可以继续拆成协议、后端、前端和验收 Task。

每个 Task 必须包含：

```yaml
source_todos:
  - 原始文档路径与章节
base_commit: 固定提交
allowed_paths:
  - 允许修改范围
forbidden_paths:
  - 禁止修改范围
codex_e2e: required | not_applicable
```

### 6.2 风险与 E2E

以下任务默认 `codex_e2e: required`：

- 浏览器事件；
- Create/Attach/Cancel；
- 前端统一助手；
- Skill 自动路由；
- 用户信息写入；
- Proposal 确认；
- Decision 保存和后续复用。

纯内部强类型契约、尚未接入产品路径的 Registry 可以标记
`codex_e2e: not_applicable`，但仍需 Codex 独立审查。

### 6.3 Review Gate

```text
Codex 写 Task
→ Grok 实现、测试、自审并写 Handoff
→ Codex Review
→ Codex 执行必要的 Browser / Computer Use E2E
→ Grok 按集中 Review 修复
→ Codex 复验并 accepted
```

### 6.4 验收节奏

不等待所有 Task 完成后再统一验收。默认采用三层门禁：

1. **Task 级即时验收**：Grok 完成一个 Task 后立即执行代码层验证并停止；Codex
   随即审查 diff、契约和风险，并执行该 Task 要求的最小产品 E2E。只有
   `accepted` 后，依赖它的 Task 才能进入 `ready`；
2. **业务轮次级验收**：可信运行、统一 Agent、个人 Wiki 等业务轮次完成时，集中
   验证完整用户旅程、跨 Task 接口、上轮回归和局部回滚，发现问题时形成下一轮
   Review 或修复 Task；
3. **产品级最终验收**：TASK-024 使用 Browser / Computer Use 完整执行秋招 MVP
   12 步唯一链路；TASK-027 再做发布准备与人工门禁。

Task 级验收只验证当前边界和必要回归，不为每个小 Task 重跑完整 12 步链路。已经
接受的 Task 若在后续集成中暴露回归，不改写历史结论，通过受影响 Task 的 Review
或新的修复 Task 处理。

### 6.5 局部回滚与兼容窗口

每轮进入 `ready` 前冻结：

- 服务端能力控制或等价流量切换；
- 上一轮 accepted commit/部署；
- 关闭后的前端、API、运行中请求和历史读取行为；
- Migration 前向兼容和数据保留；
- 依赖闭包、停止条件和回滚成功判据。

默认回滚为：

```text
关闭当前业务能力
→ 切回上一 accepted 应用组合
→ 必要时回退当前轮代码
```

数据库采用 Expand–Migrate–Contract。常规回滚保留新 Schema 和用户数据，不执行删表、
删列或删除 Wiki Revision、Decision、Review、Run 等记录。破坏性 Contract 与兼容
代码清理必须单独建 Task，并至少等待下一个依赖业务轮次验收通过。

完整轮次和回滚矩阵见
[`业务交付轮次`](../../collaboration/rounds/README.md)。

## 7. 当前明确不做

- 重写 Research/Fortune Workflow；
- 为 Skill 建立第二套 Agent Runtime；
- 为每个 Skill 建立独立数据库或独立用户身份；
- 多 Skill 自动协作；
- 模型选择器 UI；
- 股票 Skill；
- Obsidian 实时双向同步；
- Skill 自动修改和发布；
- 知识图谱；
- 多 Agent 自由协作；
- MCP/Skill 市场；
- 大规模 Worker 池和跨地域调度；
- 未经用户授权的生产默认切换。

## 8. 立即下一步

完整 Task 依赖、业务轮次和状态见
[`迁移 Backlog`](../../collaboration/tasks/BACKLOG.md)。

```text
1. 确认本方案与现有产品文档
2. 将产品、架构和协作文档形成基准提交
3. 用户明确授权 ROUND-01
4. 固定 ROUND-01 与 TASK-002 的 base_commit
5. 创建 Grok TASK-002 worktree
6. 逐个执行并即时验收 TASK-002～TASK-007
7. Codex 完成 ROUND-01 业务 E2E、上轮基线回归和回滚/重新启用演练
8. ROUND-01 accepted 后停止，等待用户是否授权 ROUND-02
```

TASK-001 属于 ROUND-02。虽然它技术上可以提前建立纯 Skill 契约，但默认不跨轮提前
执行，避免重新形成一条超出当前用户授权的长程任务。任何 Skill 请求链、统一助手
前端和新产品数据接入，都必须遵守业务轮次门禁。

# Agent Runtime 迁移状态

> 更新日期：2026-07-29
>
> 目标架构：[`agent-runtime.md`](agent-runtime.md)
>
> 开发分支：`codex/agent-runtime-migration`
>
> 状态：迁移代码已合入 `main`；显式取消修复已通过产品验收，生产默认切换仍需完成剩余门禁

## 结论

本轮迁移的代码目标已经收口。Python 不再同时维护新旧 Agent 架构：

```text
Legacy HTTP Adapter ─┐
                     ├─> ExecutionRegistry
V1 Agent Run API ────┘
                          -> LangGraphV1Runtime
                          -> AgentApplication
                          -> Compiled Root Graph
                          -> chat_v1 / research_v1 / fortune_v1
                          -> ModelGateway / Capability Registry
```

旧 `stream_graph`、旧 Builder/节点、旧 RAG Agent、旧 Provider 直连路径、重复
Tool/Worker/依赖文件已经删除。Legacy 只做协议映射。

生产尚未切换。生产 Compose 有意保留：

```dotenv
AGENT_PROTOCOL_MODE=legacy
AGENT_RUNTIME_STORE=memory
AGENT_RUNTIME_COORDINATION=none
```

切换 `v1 + postgres + redis` 必须经过人工审核、数据库准备和小流量观察。

## 已完成

### 单一执行架构

- 一个 `AgentApplication`、一个 Root Graph、一个 Runtime Coordinator；
- Chat、Research、Fortune 是独立 Subgraph；
- HTTP Handler 不导入节点，不创建模型，不执行工具；
- Legacy/V1 复用同一执行链；
- Python 只允许 `AGENT_EXECUTION_ENGINE=langgraph_v1`；
- 架构守卫测试阻止旧目录、旧 import 和重复依赖重新进入。

### LangGraph 工作流

- Chat：无工具模型流式回答；
- Research：结构化计划、LangGraph `Send` fan-out、reducer、显式 Join、证据评分、
  预算化补检索、内容寻址 Evidence Artifact 与引用合成；
- Fortune：结构化 BirthProfile、缺字段澄清、确定性八字/紫微能力、Chart Artifact
  与模型解释；
- deadline、显式取消、模型/工具预算、部分失败降级和失败关闭均进入统一
  RunContext。

命理知识库、认知镜像、决策实验室和复盘属于后续产品能力，不是本轮 Runtime
迁移阻塞项。

### Model 与 Capability 边界

- 百炼通过 OpenAI-compatible Provider 接入；
- Workflow 只依赖 Model Gateway，不读取 Key、不创建 Provider Client；
- streaming、usage、JSON/structured output 与稳定错误码统一；
- structured output 有界修复，最多三次总调用；
- AgentSpec、Alias、Model Profile、Prompt Bundle、Capability 白名单与预算真实生效；
- Capability 具备版本、强类型 schema、effect、idempotent、shadow、deadline 和
  资源策略；
- 当前正式能力均为只读幂等。非幂等能力在 durable operation ledger 落地前会被
  readiness 拒绝，避免恢复时重复外部副作用。

### 持久 Runtime 与多副本基础

- `005_agent_runtime_foundation.sql` 建立独立 `agent_runtime` schema；
- PostgreSQL 保存 execution、Event Outbox、Artifact staging、lease/fencing 与
  LangGraph checkpoint；
- `starting_after` 可跨连接、进程和副本回放；
- 单调 `lease_epoch` 阻止旧 owner 在接管后继续写事件、Artifact 或 checkpoint；
- 进程崩溃后，第二 owner 在 lease 到期后从 checkpoint 恢复；
- Redis pub/sub 加速事件唤醒和取消通知；失败时 PostgreSQL 轮询仍可工作；
- retention 维护任务清理 execution、event、artifact 与 checkpoint；
- `scripts/setup_agent_runtime.py` 将 checkpoint 建表从生产请求生命周期中分离。

真实进程强杀测试会启动独立 Worker、在模型节点阻塞时终止操作系统进程，再由第二
进程以更高 lease epoch 接管；验证事件序号连续、`run.started` 只出现一次、
`run.resumed` 只出现一次并最终完成。

### 传输与产品 Run

- V1 事件序号严格连续；缺口有限回放，无法追平时失败关闭；
- 浏览器断开不再自动取消语义 Run；
- Go 会按最后确认序号在后台续接并持久化最终答案；
- Go Run-ID 取消接口与 Python 取消传播已经实现；
- Python Event 先落 Store 后推流，Go 再持久化脱敏关键事件和 Span。

### P0 修复完成：显式停止终态一致

2026-07-30 已修复“页面显示已停止、后台 Run 仍继续运行”的状态分裂：

- 前端不再把本地 `AbortError` 当作停止成功，只接受服务端终态事件；
- 点击停止后进入“正在停止生成”，取消请求失败时保留运行状态并允许重试；
- Go 先将 `cancel_requested` 持久化，再向 Python 传播取消；
- `cancel_requested` 与晚到的 `run.completed` 发生竞态时，以 `cancelled` 为最终状态；
- Product Run 与 assistant message 在同一事务中分别落为 `cancelled/stopped`；
- Go 将数据库确定的最终状态投影给浏览器，页面、消息和 Run 不再各自推断。

自动测试覆盖取消/完成竞态、消息终态和会话解锁；真实页面验收确认 DELETE 成功、
页面显示“已停止生成”，数据库为 `cancelled/stopped`，同一会话随后可正常产生
`completed/completed` 的新 Run。浏览器意外断开仍只代表 detach，不会自动转换为
显式取消。

### P0 修复完成：运行事件与回答正文分离

2026-07-31 已完成 TASK-002 的浏览器事件分层：

- Go 通过纯白名单投影将 route/progress/model/tool 映射为结构化 `activity`；
- `artifact.created` 只投影安全引用元数据，不发送 Artifact 内容；
- V1 只有 `answer.delta` 映射为 `answer_delta` 并进入持久化正文；
- 前端使用强类型协议和纯 reducer 分离 answer、activity、artifact 与终态；
- legacy `isThinking=true` delta 转换为通用 Activity，不进入正文或复制内容；
- Activity 在回答上方使用独立、可折叠、键盘可操作的展示区域；
- Go 投影/集成测试和前端 reducer 单元测试覆盖白名单、sequence、重复事件、
  五次工具调用、legacy、Artifact 和终态不污染正文。

该修复不改变生产默认协议模式、取消状态机、检索次数、Citation、Skill 或模型配置。
生产切换仍受本文件后续数据库准备、小流量观测和用户授权门禁约束。

### 可观测与 provenance

- Model Gateway 自动发布 started/completed/failed、duration 与 usage；
- Capability Executor 自动发布工具生命周期、指纹和耗时；
- Prompt 文件/hash、AgentSpec hash、Workflow/version、Provider/Profile/Model、
  Capability/version/effect/idempotence 与服务/协议/Graph 版本在创建 Run 时一次性
  封存；
- Python 首次创建后不在重连或接管时重写 provenance；
- Python 与 Go 两层脱敏，不记录密钥、完整 Prompt、工具明文或模型隐式思维链。

### 依赖与容器

- Python `>=3.11,<3.13`；
- `pyproject.toml + uv.lock` 是唯一依赖锁定来源；
- 删除所有 `requirements*.txt` 与拆分 requirements；
- Docker 固定 Python 3.11.14 和 uv 0.9.18；
- 最终 Python 镜像不包含 Node/npm；
- 旧 LangChain/LlamaIndex/RAG/本地大模型与未使用 Worker 依赖已退出运行时。

## 自动验收结果

迁移分支最后一次完整验证：

| 项目 | 结果 |
|---|---|
| Python 3.11 target unit | 62 passed，2 skipped |
| 真实 PostgreSQL integration | 2 passed |
| 真实 OS process kill/takeover | passed |
| Go `go test ./...` | passed |
| Ruff | passed |
| `uv lock --check` | passed |
| Docker build | passed |
| 容器 readiness/编译 smoke | passed |
| 最终镜像无 Node/npm | passed |
| Compose config | passed |
| `git diff --check` | passed（仅 Git 行尾提示） |
| P0 Product Run 风险矩阵（2026-07-31） | 11 suites passed，9 risks passed |

P0 的统一入口、隔离数据库要求、状态语义和报告位置见
[`p0-runtime-acceptance.md`](../operations/p0-runtime-acceptance.md)；风险到可定位测试的
映射由 `scripts/p0_runtime_matrix.json` 维护。报告不保存命令输出、用户内容、Prompt
或环境变量值。

真实 Provider smoke 在迁移期间已验证百炼 Chat 流式与 Fortune 结构化提取；最终回归
不读取或输出真实 Key，也不把外部 Provider 可用性作为本地架构测试前提。

## 仅剩人工参与

以下操作仍需人工参与。它们有生产影响，自动迁移不会代替人工执行：

1. 生产 PostgreSQL 备份并确认可恢复；
2. 由数据库管理员执行 migration、checkpoint setup 与最小权限 grant；
3. 配置生产 Secret、Runtime 数据库连接和 Redis；
4. 在测试/小流量环境切换 `v1 + postgres + redis` 并观察；
5. 确认指标后逐步扩大流量；
6. 最终授权生产默认切换。

详细命令、门禁、观测点和回滚方法见
[`agent-runtime-rollout.md`](../operations/agent-runtime-rollout.md)。

P0 的协议、实施顺序和自动验收矩阵见
[`agent-runtime-p0-stabilization-plan.md`](agent-runtime-p0-stabilization-plan.md)。

## TODO 优先级与迁移门禁

### P0：V1 默认开放前必须完成

1. 修复显式取消的 Run-ID 时序缺口，保证页面、Go Run、Python execution 和消息
   最终状态一致；
2. 已完成（2026-07-31）：运行事件与最终正文分层，`tool/progress` 保持结构化事件，
   `answer.delta` 才能进入最终消息；实时页面、刷新结果和复制内容保持一致；
3. 已完成（2026-07-31）：服务重启恢复、失败/超时解锁、事件序号、
   Trace/provenance 脱敏和跨用户权限已纳入统一自动技术验收；隔离 PostgreSQL 的
   `full` profile 验证为 11 suites passed、9 risks passed。

迁移实现可以保存在 `main`，但生产 Compose 必须继续保持 legacy 默认链路，直到
上述剩余 P0 自动门禁、生产数据库准备和小流量观测全部完成。代码合入不等于生产
默认切换授权。

### P1：下一轮产品架构迁移

1. 先建立 Model Catalog、稳定 `model_id`、Skill Registry 以及
   `requested_skill/resolved_skills` Run 契约；
2. 再把产品收敛为单一助手模式，将 Research/Fortune 迁为统一助手背后的 Skill
   和受控 Subworkflow，逐步废弃前端 `agent_name` 模式选择；
3. 最后增加模型选择器、Skill 快捷按钮、composer chip 和结构化运行活动区。

P1 的后端契约必须先于前端按钮。不得先为 Fortune 或新的专业 Agent 增加独立模式，
否则会继续扩大即将废弃的多模式分支。

### P2：质量、成本和体验优化

- Research 自适应 0/1/N 检索与证据充分度策略；
- Skill 自动路由、显式选择、模型兼容和误触发 Eval；
- 工具活动区的折叠、来源、耗时和 Artifact 展示；
- Fortune 知识、解释质量、免责声明和领域审核。

### P3：后续平台能力

- 认知镜像、记忆确认/遗忘；
- 决策实验室和复盘；
- 写能力 durable operation ledger；
- MCP/第三方 Skill 市场；
- 更大规模 Worker 池和跨地域调度。

## 非迁移阻塞的后续工作

### 产品架构主线 TODO 1：单一助手模式与模型选择

- 移除前端“普通/深度思考”对内部
  `default_llm_agent/research_agent` 的直接选择，产品层始终只有一个助手模式；
- “是否进行模型内部推理”由当前模型的原生能力、服务端 Model Profile 和任务上下文
  决定，不再用产品按钮切换 Agent。产品不得展示或持久化模型隐式思维链，只展示
  可验证的执行进度、工具活动和最终答案；
- 会话顶部提供产品模型选择器。默认使用一个 `auto/default` 模型，用户切换
  `model_id` 只影响后续 Run；一次 Run 使用创建时解析并冻结的有效模型配置；
- `model_id -> provider/profile/capabilities/limits` 由 Model Catalog 解析。最终
  Provider、模型版本、参数和策略快照进入 provenance；前端不得提交任意 base URL、
  Provider 参数或内部 Profile 名；
- 产品层只有一个模式不等于 Runtime 只有一条路径。Root Agent 仍可按请求选择直接
  回答、受控 Tool Loop 或 Research/Fortune Subworkflow。

### 产品架构主线 TODO 2：Skill 化专业能力

- 将 Fortune、Research 以及后续文件分析、决策、复盘等能力注册为统一助手可发现的
  Skill；Skill 封装触发说明、专业指令、输入/输出 schema、允许的 Capability、
  Subworkflow、预算、风险策略和 UI 元数据；
- 默认由 Root Agent 根据 Skill 元数据和用户请求自动选择；前端可以提供 Skill
  快捷按钮，但按钮语义是为当前请求设置 `requested_skill`，不是切换并长期锁定
  整个 Agent 模式；
- 显式 Skill 请求优先于自动路由，但仍必须经过权限、模型能力、输入完整性和风险
  校验。按钮应以可移除的 composer chip 呈现，例如“命理分析”，执行完后回到统一
  助手；
- Research/Fortune 现有 Workflow 不删除，分别成为 Skill 背后的受控 Subworkflow；
  农历、八字、紫微、联网检索等确定性动作继续属于 Capability/Tool，不塞进自由执行
  的提示词脚本；
- API 从 `agent_name` 产品选项收敛为稳定的 `model_id` 与可选
  `requested_skill`。每个 Run 记录 `requested_skill/resolved_skills`、Workflow、
  Capability 和模型快照，保证可回放和可审计；
- 允许模型自动提出工具调用，但必须经过 Capability Registry 的 allowlist、schema、
  deadline、预算、幂等、副作用和权限校验。简单对话默认 0 次工具调用，不能把统一
  模式实现成每条消息默认联网检索。

### 其他产品与平台 TODO

- 命理知识 Capability；
- Research 自适应检索预算：当前计划模型最多生成 5 个查询，`research_agent`
  的 `max_tool_calls` 也配置为 5，工作流会在预算内并行执行这些查询。它不是无条件
  写死调用五次，但简单问题也容易耗尽五次预算；后续应根据问题复杂度、查询去重、
  首轮证据充分度和成本策略动态决定 0/1/N 次检索；
- 工具活动与最终正文分层：当前 Go 将 `tool.completed` 投影成普通文本
  `delta`（“已完成工具：...”），前端再把它与 `answer.delta` 累积到同一正文。
  后续必须保持结构化事件类型，在前端使用独立、可折叠的运行活动区展示计划、检索、
  工具状态和耗时；最终回答只消费 `answer.delta`。同时保证实时页面、刷新后的持久
  消息和复制内容一致；
- 结构化 Citation 展示（P2，非当前取消修复合码阻塞）：Research 已生成由来源 URL
  派生的 `citation_id`，模型也会在正文中输出 `[citation_id]`，但 Go 尚未把 Citation
  Artifact 投影到浏览器协议，前端只能将内部 ID 当作普通 Markdown 文本显示。后续
  必须将 `citation_id/title/url/snippet/source_type` 作为结构化引用随 Run 和消息
  持久化，由 Go 投影给实时流与历史消息，前端渲染为可点击的 `[1]`、`[2]` 角标和
  回答底部来源列表；刷新、复制和重新附着后的引用语义必须一致。不得仅用正则隐藏
  ID，也不得在没有结构化来源元数据时把任意方括号文本改写成链接；
- 认知镜像、记忆确认/遗忘；
- 决策实验室和复盘 Workflow；
- 写能力的 durable operation ledger；
- 产品级质量 Eval 与长期业务指标；
- MCP/Skill/受限 Draft Workflow；
- 更大规模 Worker 池与跨地域调度。

这些功能必须扩展现有 `AgentApplication / Workflow / Capability / ModelGateway /
RuntimeEvent` 接口，不能建立第二个 Runtime。

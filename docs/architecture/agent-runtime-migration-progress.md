# Agent Runtime 迁移状态

> 更新日期：2026-07-29
>
> 目标架构：[`agent-runtime.md`](agent-runtime.md)
>
> 开发分支：`codex/agent-runtime-migration`
>
> 状态：主体实现与自动验证完成；等待人工验收，显式取消时序问题列为默认开启前的 P0 TODO

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

### P0 TODO：显式停止存在 Run-ID 获取时序缺口

2026-07-29 的真实页面验收发现，前端点击“停止生成”后可能只中止浏览器 SSE，
后台 Run 仍继续执行并最终写成 `completed`。用户紧接着发送下一条消息时，会收到
`conversation_busy`。

这不是 LangGraph、PostgreSQL Runtime Store 或 Python CancellationToken 本身失效，
而是产品控制面与流式传输之间的契约缺口：

1. 前端只有收到当前 SSE 中的 `meta.run_id` 后，才能调用
   `DELETE /api/v1/agent-runs/{runID}`；
2. “停止”按钮在请求发出后立即可用，用户可能在 `meta` 到达前点击；
3. 这一取消意图目前只暂存在 React 内存引用中，没有持久的请求身份或服务端取消意图；
4. 取消 API 失败时，前端会中止本地流并显示“已停止”，从而可能掩盖后台 Run 未取消；
5. Go 当前只能按 `run_id` 取消，不能按已知的
   `conversation_id + client_message_id` 查找或登记待取消意图。

因此，“浏览器 detached 不等于语义取消”的架构原则仍然正确，但显式停止必须拥有
一条不依赖同一条 SSE 先交付 Run ID 的稳定控制通道。

建议按两层收口：

- 短期：增加按 `conversation_id + client_message_id` 的幂等取消命令。Go 在 Run
  已创建时解析并取消；Run 尚未创建时短暂等待或持久化 pending-cancel intent。
  前端从发送开始就持有这两个 ID，取消失败时不得把 UI 标记为成功停止。
- 目标：将“创建 Run”和“订阅事件”拆成两个协议步骤。创建命令先返回稳定
  `run_id/execution_id`，随后客户端用独立 SSE attach/re-attach；取消始终走独立
  command endpoint。这样 start、attach、detach、cancel 四种语义完全分离。

修复后的强制验收：

- 在首个 `meta` 前立即点击停止，Run 和 assistant message 最终均为 `cancelled`；
- 在模型流式输出中点击停止，同样落为 `cancelled`；
- 取消 API 故障时 UI 明确显示取消失败，不得伪装成“已停止”；
- 取消完成后同一会话可立即发送下一条消息；
- 重复取消幂等，多副本下由 PostgreSQL 状态和 fencing 保证唯一终态；
- 浏览器意外断开仍只 detach，不自动转换为显式取消。

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
| Python 3.11 target unit | 61 passed |
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

真实 Provider smoke 在迁移期间已验证百炼 Chat 流式与 Fortune 结构化提取；最终回归
不读取或输出真实 Key，也不把外部 Provider 可用性作为本地架构测试前提。

## 仅剩人工参与

以下操作仍需人工参与。它们有生产影响，自动迁移不会代替人工执行。显式取消 P0
TODO 可以与后续产品问题集中整改，但在 V1 成为默认链路前必须修复并通过上述验收：

1. 审核本分支的大规模删除、状态所有权与安全边界；
2. 选择提交拆分方式、合并到 `main` 并推送；
3. 生产 PostgreSQL 备份并确认可恢复；
4. 由数据库管理员执行 migration、checkpoint setup 与最小权限 grant；
5. 配置生产 Secret、Runtime 数据库连接和 Redis；
6. 在测试/小流量环境切换 `v1 + postgres + redis` 并观察；
7. 确认指标后逐步扩大流量；
8. 最终授权生产默认切换。

详细命令、门禁、观测点和回滚方法见
[`agent-runtime-rollout.md`](../operations/agent-runtime-rollout.md)。

P0 的协议、实施顺序和自动验收矩阵见
[`agent-runtime-p0-stabilization-plan.md`](agent-runtime-p0-stabilization-plan.md)。

## TODO 优先级与迁移门禁

### P0：V1 默认开放前必须完成

1. 修复显式取消的 Run-ID 时序缺口，保证页面、Go Run、Python execution 和消息
   最终状态一致；
2. 修复运行事件与最终正文的协议混用：`tool/progress` 保持结构化事件，
   `answer.delta` 才能进入最终消息；实时页面、刷新结果和复制内容必须一致；
3. 完成服务重启恢复、失败/超时解锁、事件序号、Trace/provenance 脱敏和跨用户权限
   的自动技术验收并形成报告。

本项目采用“`main` 保持可验收、可发布”的合码标准：P0 未完成时可以在迁移分支
继续提交、推送和内部架构开发，但不合入 `main`，也不得把 V1 设为面向用户的默认
链路。只有 P0 修复、自动技术验收报告和完整回归全部通过后，才进入人工审核与
`main` 合并。

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
- 认知镜像、记忆确认/遗忘；
- 决策实验室和复盘 Workflow；
- 写能力的 durable operation ledger；
- 产品级质量 Eval 与长期业务指标；
- MCP/Skill/受限 Draft Workflow；
- 更大规模 Worker 池与跨地域调度。

这些功能必须扩展现有 `AgentApplication / Workflow / Capability / ModelGateway /
RuntimeEvent` 接口，不能建立第二个 Runtime。

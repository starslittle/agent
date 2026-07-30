# Agent Runtime P0 稳定化方案

> 状态：待实施
>
> 范围：当前 Runtime 迁移分支合入 `main` 前的发布阻塞项
>
> 关联文档：
> [`agent-runtime.md`](agent-runtime.md)、
> [`agent-runtime-migration-progress.md`](agent-runtime-migration-progress.md)、
> [`agent-runtime-rollout.md`](../operations/agent-runtime-rollout.md)

## 1. 目标

本阶段不增加新的产品 Agent、模型选择器或 Skill UI，只解决以下三个 P0：

1. 用户显式停止必须可靠到达后台，不能只断开浏览器流；
2. Tool/Progress 事件必须与最终回答正文分离；
3. 用自动故障注入完成恢复、一致性、失败关闭、Trace 和权限验收。

完成后，迁移分支必须满足：

- `main` 合入后仍是可验收、可发布状态；
- V1 Run 的开始、订阅、取消和终态不依赖某一个浏览器连接；
- 页面、Go Product Run、Python execution 和消息具有确定的状态映射；
- 实时回答、刷新后的回答和复制内容完全一致；
- 所有验收可以由自动脚本重复执行，不要求产品负责人操作数据库或制造故障。

## 2. 非目标

以下内容属于 P1/P2，不进入本阶段：

- 删除“深度思考”并上线统一助手；
- Model Catalog、模型选择器；
- Skill Registry、Research/Fortune Skill 化；
- Fortune 产品入口；
- Research 自适应检索质量优化；
- 工具活动区的完整视觉设计；
- 新的写操作 Capability。

P0 只建立这些能力未来依赖的稳定 Run 和事件协议。

## 3. 当前问题

### 3.1 取消依赖同一条 SSE 先交付 Run ID

当前流程：

```text
浏览器 POST 流式消息
→ Go 创建 Product Run
→ Go 连接 Python 流
→ Go 通过同一条 SSE 发送 meta.run_id
→ 前端拿到 run_id 后才能 DELETE Run
```

停止按钮在 `meta.run_id` 到达前已经可用。此时用户点击停止，取消意图只能暂存在
React 内存；取消接口失败时，前端还会中止本地流并显示“已停止”。真实验收已经发现：

```text
页面：已停止
Go Run：running → completed
Python execution：completed
下一条消息：conversation_busy
```

### 3.2 运行事件被伪装成回答正文

Go 当前将 `tool.completed` 转换成
`delta("已完成工具：tavily_search\n")`。前端无法区分 Tool 活动和
`answer.delta`，最终把二者拼进同一个 Markdown 正文。

Go 持久化的 assistant message 又只包含真正的 `answer.delta`，因此实时页面和
刷新后可能不一致。

### 3.3 技术验收没有形成单一报告

底层已经存在单元、PostgreSQL integration 和进程强杀测试，但尚未形成一份以产品
Run 为中心的 P0 验收报告，不能一眼确认：

- Python 重启后是否恢复；
- 失败/超时后会话是否解锁；
- Go/Python/message 状态是否一致；
- 事件是否连续、幂等；
- Trace/provenance 是否完整且脱敏；
- 跨用户访问是否被拒绝。

## 4. 核心设计决策

### 4.1 创建 Run 与订阅事件分离

不继续修补“在同一条 SSE 中等待 Run ID”的协议。目标产品 API 分为三个独立动作：

```text
Create Run
Attach / Re-attach Events
Cancel Run
```

目标流程：

```text
POST message
→ Go 事务创建 user message / assistant message / Product Run
→ 立即返回 run_id、execution_id、message ids
→ Go Run Supervisor 在后台启动或恢复 Python execution

GET Run events
→ 浏览器按 sequence 订阅或重新附着
→ 浏览器断开只影响订阅，不改变 Run 语义

DELETE Run
→ Go 标记 cancel_requested
→ 传播到 Python CancellationToken
→ 等待并返回确定终态
```

前端只有在 Create Run 成功并获得 `run_id` 后才展示“停止生成”。因此不存在
“停止按钮已经可点，但后台身份尚不可寻址”的窗口。

### 4.2 Go Run Supervisor 拥有产品执行

浏览器 Handler 不再拥有 Python execution 生命周期。新增 Go Run Supervisor，
职责包括：

- 启动或恢复 Python V1 execution；
- 消费严格递增的 Runtime Event；
- 处理缺口回放和有限重连；
- 持久化结构化事件和 Trace 投影；
- checkpoint assistant answer；
- 写入 Product Run/message 唯一终态；
- 响应显式取消；
- 浏览器为零订阅者时继续运行；
- Go 重启后扫描活动 Run 并进行状态对账或恢复。

Supervisor 不执行模型、工具或 LangGraph 节点；它只是 Go 产品控制面中的 Run
拥有者。Python Runtime Store 仍是 execution/checkpoint/event outbox 的事实源。

首轮实现允许单 Go Gateway owner，但所有写入必须保持幂等。若部署多个 Gateway，
必须先使用 PostgreSQL claim/lease 或等价的唯一 owner 机制，不能依赖进程内 map
决定所有权。

### 4.3 结构化事件端到端保真

Python 的稳定事件类型不再被改写成回答文本。浏览器协议至少区分：

```text
meta
activity
answer_delta
artifact
done
error
```

映射规则：

| Python Runtime Event | Browser Event | 是否进入正文 |
|---|---|---|
| `route.selected` | `activity` | 否 |
| `progress` | `activity` | 否 |
| `model.started/completed/failed` | `activity` | 否 |
| `tool.started/completed/failed/cancelled` | `activity` | 否 |
| `artifact.created` | `artifact` | 否 |
| `answer.delta` | `answer_delta` | 是 |
| `run.completed/cancelled/failed/timed_out` | `done` | 否 |

前端 assistant message 的 `content` 只能由 `answer_delta` 累积。复制、Markdown
渲染和数据库最终正文必须使用同一份 answer。

Activity 只显示经过服务端白名单投影的产品信息，不显示完整 Prompt、模型隐式思维
链、Tool 明文输入、API Key、Token、Cookie、未脱敏异常或连接字符串。

## 5. 产品 API

### 5.1 创建消息与 Run

```http
POST /api/v1/conversations/{conversation_id}/runs
X-CSRF-Token: ...
Content-Type: application/json
```

```json
{
  "content": "用户问题",
  "client_message_id": "uuid",
  "agent_name": "research_agent"
}
```

P0 保留 `agent_name` 兼容字段；P1 再替换为 `model_id/requested_skill`。

成功返回 `202 Accepted`：

```json
{
  "conversation_id": "uuid",
  "user_message_id": "uuid",
  "assistant_message_id": "uuid",
  "run_id": "uuid",
  "execution_id": "exec_...",
  "protocol_version": 1,
  "status": "queued",
  "events_url": "/api/v1/agent-runs/{run_id}/events"
}
```

`client_message_id` 继续作为幂等键。重复请求返回同一个 Product Run，不得创建第二个
execution。

### 5.2 订阅与重新附着

```http
GET /api/v1/agent-runs/{run_id}/events?starting_after=42
Accept: text/event-stream
```

要求：

- 校验 Run 所有权；
- 每个事件携带严格递增 `sequence`；
- `starting_after` 支持刷新和断线重连；
- 重放事件与实时事件不得重复；
- Run 已终止时仍能返回最终 `done`；
- 浏览器断开不得触发 Cancel。

浏览器事件示例：

```json
{
  "type": "activity",
  "sequence": 17,
  "activity": {
    "kind": "tool",
    "status": "completed",
    "label": "联网检索"
  }
}
```

```json
{
  "type": "answer_delta",
  "sequence": 18,
  "data": "最终回答的一部分"
}
```

### 5.3 显式取消

继续使用：

```http
DELETE /api/v1/agent-runs/{run_id}
X-CSRF-Token: ...
```

语义：

- `queued/running` 原子转换为 `cancel_requested`；
- queued 且尚未启动 Python 时，由 Supervisor 直接关闭为 `cancelled`；
- Python execution 已存在时，调用 Python DELETE 并等待 `run.cancelled`；
- 重复 DELETE 幂等返回已有终态；
- 取消失败时返回稳定错误，前端不得伪装成功；
- 超过取消等待时间后保持 `cancel_requested` 并继续后台对账，不能回退为 running。

## 6. 状态机与一致性

### 6.1 Product Run

```text
queued
→ running
→ completed | cancelled | failed | timed_out

queued | running
→ cancel_requested
→ cancelled | failed | timed_out
```

终态不可逆，迟到的 `run.completed` 不得覆盖 `cancelled`。

### 6.2 状态映射

| Python execution | Go Product Run | Assistant message |
|---|---|---|
| `queued/running` | `queued/running` | `streaming` |
| `cancel_requested` | `cancel_requested` | `streaming` |
| `cancelled` | `cancelled` | `stopped` |
| `completed` | `completed` | `completed` |
| `failed` | `failed` | `failed` |
| `timed_out` | `timed_out` | `failed` |

消息 schema 当前使用 `stopped` 表示用户取消，不新增含义重复的 `cancelled`。

### 6.3 最终答案不变量

```text
assistant_message.content
==
按 sequence 拼接的全部 answer.delta
```

Activity、Tool 名称和进度文本不得进入这个等式。

## 7. 前端改造

`ChatContainer` 使用明确状态：

```text
idle
submitting
queued
streaming
cancelling
completed | stopped | failed
```

行为：

1. `submitting` 阶段显示提交状态，不展示 Stop；
2. Create Run 返回后保存 `run_id`，开始 Attach 并展示 Stop；
3. 点击 Stop 后进入 `cancelling`，按钮禁用，调用 DELETE；
4. 只有收到取消终态才显示“已停止生成”；
5. DELETE 失败时显示“取消失败，任务仍在运行”，继续订阅；
6. `answer_delta` 更新正文；
7. `activity` 更新独立的结构化活动列表；
8. 刷新后按 Run status、assistant message 和事件游标恢复页面。

P0 可以先使用简单折叠列表展示 activity；完整视觉设计留到 P2。

## 8. 自动验收矩阵

### 8.1 取消

- Run 创建后、Python 启动前取消；
- 模型流式输出中取消；
- Tool 执行中取消；
- 重复取消；
- 取消 API 返回错误；
- 取消与自然完成竞态；
- 浏览器断开但未显式取消；
- 取消后立即在同一会话发送下一条消息。

断言：

- 不存在永久 `running/cancel_requested`；
- cancelled Product Run 不会被迟到 completed 覆盖；
- message 最终为 `stopped`；
- 下一轮可以创建。

### 8.2 重启恢复

- 在模型节点阻塞时重启 Python Agent；
- 在 Tool 节点阻塞时重启 Python Agent；
- 重启后从 PostgreSQL checkpoint/outbox 恢复；
- 事件 sequence 连续；
- `run.started` 不重复；
- 最终完成且答案不重复；
- 可选增强：重启 Go Gateway 后 Supervisor 恢复活动 Run。

### 8.3 失败与超时

- 模型返回可重试错误并耗尽重试；
- 模型调用超过绝对 deadline；
- Tool 抛出失败；
- Tool 不响应并超时；
- Python 内部流断开且无法在重连预算内恢复；
- 事件 sequence gap 无法回放。

断言：

- Run 进入 `failed/timed_out`；
- assistant message 进入 `failed`；
- error code 稳定且脱敏；
- 会话活动 Run 唯一索引被释放；
- 下一轮可以创建。

### 8.4 事件与正文

- 五次 `tool.completed` 不进入 assistant content；
- Activity 事件保持原顺序；
- answer delta 无遗漏、无重复；
- 实时正文、刷新正文、复制正文一致；
- reconnect `starting_after` 不重复事件；
- Artifact 与正文分别投影。

### 8.5 Trace 与 provenance

每个 Run 检查：

- `trace_id/execution_id/run_id` 可关联；
- AgentSpec、Workflow/version、Prompt hash、Provider、Profile、Model 有快照；
- Model/Tool Span 有开始、结束、耗时和稳定状态；
- 不包含 Key、Cookie、Token、数据库密码、完整 Prompt 或隐式思维链；
- 当前模型名与实际 Provider 返回一致。

### 8.6 权限隔离

使用两个自动创建的测试用户：

- 用户 B GET 用户 A 的 Run：不可见；
- 用户 B Attach 用户 A 的 events：不可见；
- 用户 B DELETE 用户 A 的 Run：不可取消；
- 用户 B 不可通过 conversation、message、trace ID 推断用户 A 数据；
- 错误响应不泄露资源是否真实存在。

## 9. 实施顺序

### Commit 1：测试基线与协议类型

- 先添加失败测试和新的 API/Event 类型；
- 固定状态矩阵与终态覆盖规则；
- 不改变生产行为。

### Commit 2：Go Run Supervisor 与 Create/Attach

- 抽取当前 `streamV1/continueV1Detached` 的执行拥有逻辑；
- 新增 Create Run、Attach events；
- 增加启动恢复与幂等终态；
- 保留旧 stream endpoint 作为临时兼容适配器，内部调用新服务；
- 标记旧 endpoint deprecated，不建立第二套执行实现。

### Commit 3：显式取消

- Stop 只使用已返回的 `run_id`；
- queued/running/cancel_requested 全路径；
- 取消失败和竞态测试；
- 删除“取消失败也 abort 并伪装 stopped”的逻辑。

### Commit 4：结构化事件与前端状态机

- `activity/answer_delta/artifact/done` 分离；
- Chat message 只累计 answer；
- 最小 Activity 折叠区；
- refresh/reconnect 测试。

### Commit 5：自动验收与报告

- 故障注入脚本；
- 两用户隔离脚本；
- 数据库一致性断言；
- 生成 `reports/agent-runtime-p0-acceptance.md`；
- 完整回归、Compose smoke 和真实本地页面 smoke。

## 10. 兼容与回滚

- 生产 Compose 在 P0 验收前继续默认 `AGENT_PROTOCOL_MODE=legacy`；
- 旧 stream endpoint 在迁移期保留，但只能适配到新 Run Supervisor；
- 数据库变更必须增量、可由旧镜像忽略；
- 回滚不删除 `agent_runtime` schema、checkpoint、event outbox 或新 Run 数据；
- 若新 Create/Attach 失败，切回 legacy endpoint 和上一镜像；
- 不允许通过直接修改数据库终态作为常规恢复手段。

## 11. Definition of Done

只有全部满足才允许合入 `main`：

- 所有 P0 自动验收通过；
- 真实页面完成“开始 → 流式 → 停止 → 立即继续”；
- Python 重启恢复真实执行通过；
- 实时、刷新、复制正文一致；
- 失败/超时后会话可继续；
- 两用户隔离通过；
- Trace/provenance 完整且脱敏；
- Python/Go/Frontend 完整测试和构建通过；
- Docker/Compose readiness 通过；
- `git diff --check` 通过；
- 验收报告包含提交 SHA、环境、测试命令、结果和已知非 P0 TODO；
- 人工审核状态机、API、安全边界和迁移回滚方案。

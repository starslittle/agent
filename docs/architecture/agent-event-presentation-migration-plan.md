# Agent 运行事件与回答正文分离迁移方案

> 状态：可交付 Grok 实施
>
> 优先级：P0
>
> 实施基线：从最新 `origin/main` 新建独立分支，不在旧迁移分支上继续堆叠
>
> 方案边界：只处理 Tool/Progress 等运行事件与最终回答正文混合的问题
>
> 关联文档：
> [`agent-runtime.md`](agent-runtime.md)、
> [`agent-runtime-p0-stabilization-plan.md`](agent-runtime-p0-stabilization-plan.md)、
> [`agent-runtime-migration-progress.md`](agent-runtime-migration-progress.md)

## 1. 本次迁移的结论

当前问题不是 Markdown 渲染造成的，也不是 Python Agent 把工具调用写进了最终回答。
根因位于 Go 到浏览器的事件投影层：

```text
Python tool.completed
→ Go 转换为 type=delta, data="已完成工具：tavily_search\n"
→ 前端把所有 delta 拼进 accumulatedContent
→ ChatMessage 将 accumulatedContent 当作 Markdown 正文
```

目标链路必须改为：

```text
Python AgentEvent
├─ progress/tool/model/route → Browser activity → 前端运行活动区
├─ artifact.created          → Browser artifact → 独立结构化数据
├─ answer.delta              → Browser answer_delta → assistant.content
└─ run.* terminal            → Browser done/error → 消息终态
```

迁移完成后必须始终满足：

```text
assistant_message.content
==
按事件顺序拼接的所有 answer.delta.data
```

Tool 名称、Tool 状态、Progress、Route、Model 状态和 Artifact 均不得进入这个等式。

## 2. 为什么现在必须先做

当前实现同时产生四类产品问题：

1. 页面把内部运行日志当成助手回答，正文可读性差；
2. 实时页面包含“已完成工具”，刷新后数据库正文可能不包含，产生前后不一致；
3. 复制按钮会复制工具日志，用户无法只复制回答；
4. 后续统一助手、Skill、模型选择器都会依赖结构化运行事件，现在不分层会继续扩大
   技术债。

本次迁移只修复事件投影和前端展示，不改变 Agent 的规划、检索次数、模型选择或
Workflow。

## 3. 当前代码位置

实施前必须重新核对最新 `origin/main`，但当前已知关键位置如下：

| 层级 | 文件 | 当前职责/问题 |
|---|---|---|
| Python Runtime | `backend/agent/**` | 已产生稳定的 `progress`、`tool.*`、`answer.delta` 等事件；不是本次主要修改对象 |
| Python Legacy Adapter | `backend/app/api/graph_routes.py` | 旧协议仍将 progress 映射为带 `isThinking=true` 的 `delta` |
| Go V1 投影 | `go-backend/internal/httpapi/conversations.go` | 将 `progress`、`tool.completed` 伪装为浏览器 `delta` |
| 前端协议 | `frontend/src/lib/chat-api.ts` | 目前只声明 `meta/delta/done/error` |
| 前端流状态 | `frontend/src/components/chat/ChatContainer.tsx` | 将所有 `delta.data` 拼到 `accumulatedContent` |
| 消息展示 | `frontend/src/components/chat/ChatMessage.tsx` | 通过正文字符串特征猜测“思考过程”，没有结构化 activity |
| Go 集成测试 | `go-backend/internal/httpapi/conversation_integration_test.go` | 需要增加端到端事件分层断言 |

## 4. 实施范围

### 4.1 必须完成

- 定义版本明确的浏览器流事件联合类型；
- Go V1 将运行事件投影成结构化 `activity`；
- Go V1 仅将 `answer.delta` 投影成 `answer_delta`；
- 前端只将 `answer_delta` 累积进消息正文；
- legacy 模式继续可用，但其 `isThinking=true` 的旧 `delta` 只能进入 activity；
- 前端提供最小可用的、可折叠的“运行过程”区域；
- 实时正文、刷新后的正文和复制内容保持一致；
- Tool 调用多次时按事件显示多条活动，但不显示在正文；
- 增加 Go 协议集成测试和前端事件 reducer 单元测试；
- 更新迁移进度文档和验收记录。

### 4.2 明确不做

- 不修改 Research 为什么会搜索五次；
- 不实现自适应 0/1/N 次检索；
- 不修改 Prompt、LangGraph 节点或 Capability 逻辑；
- 不实现 Citation 编号、来源列表或 Citation Artifact UI；
- 不把 Fortune/Research 改成 Skill；
- 不合并“普通模式”和“深度思考模式”；
- 不增加模型选择器；
- 不重写 Create Run/Attach/Supervisor；
- 不修改取消状态机；
- 不改变 PostgreSQL Runtime Store、checkpoint 或 Redis 协调；
- 不新增数据库表；
- 不使用正则从最终正文中删除“已完成工具”来伪装修复。

## 5. 目标浏览器事件协议

### 5.1 TypeScript 类型

在 `frontend/src/lib/chat-api.ts` 中定义等价于以下语义的类型。可以按项目格式调整
命名，但不得把不同类别重新合并为字符串正文。

```ts
export type RuntimeActivityKind =
  | "route"
  | "progress"
  | "model"
  | "tool";

export type RuntimeActivityStatus =
  | "started"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export interface RuntimeActivity {
  id: string;
  sequence?: number;
  kind: RuntimeActivityKind;
  status: RuntimeActivityStatus;
  label: string;
  name?: string;
  duration_ms?: number;
}

export type ConversationStreamEvent =
  | {
      type: "meta";
      conversation_id: string;
      user_message_id: string;
      assistant_message_id: string;
      run_id: string;
      execution_id?: string;
      protocol_version?: number;
      title: string;
    }
  | {
      type: "activity";
      sequence?: number;
      activity: RuntimeActivity;
    }
  | {
      type: "answer_delta";
      sequence?: number;
      data: string;
    }
  | {
      type: "artifact";
      sequence?: number;
      artifact: Record<string, unknown>;
    }
  | {
      // 仅用于迁移期兼容 legacy，不是 V1 的目标事件。
      type: "delta";
      data?: string;
      isThinking?: boolean;
      thinkingFinished?: boolean;
    }
  | {
      type: "done";
      message_id?: string;
      status?: string;
    }
  | {
      type: "error";
      message?: string;
    };
```

### 5.2 JSON 示例

工具开始：

```json
{
  "type": "activity",
  "sequence": 12,
  "activity": {
    "id": "12:tool:started",
    "sequence": 12,
    "kind": "tool",
    "status": "started",
    "label": "正在联网检索",
    "name": "tavily_search"
  }
}
```

工具完成：

```json
{
  "type": "activity",
  "sequence": 13,
  "activity": {
    "id": "13:tool:completed",
    "sequence": 13,
    "kind": "tool",
    "status": "completed",
    "label": "联网检索完成",
    "name": "tavily_search",
    "duration_ms": 834
  }
}
```

回答增量：

```json
{
  "type": "answer_delta",
  "sequence": 14,
  "data": "这是最终回答的一部分。"
}
```

### 5.3 Python 到浏览器的映射

| Python Event | Browser Event | 进入正文 | UI 行为 |
|---|---|---:|---|
| `route.selected` | `activity(kind=route,status=completed)` | 否 | 可选展示路线已选择 |
| `progress` | `activity(kind=progress,status=running)` | 否 | 更新运行进度 |
| `model.started` | `activity(kind=model,status=started)` | 否 | 显示正在生成 |
| `model.completed` | `activity(kind=model,status=completed)` | 否 | 显示生成完成 |
| `model.failed` | `activity(kind=model,status=failed)` | 否 | 显示阶段失败 |
| `tool.started` | `activity(kind=tool,status=started)` | 否 | 增加工具活动 |
| `tool.completed` | `activity(kind=tool,status=completed)` | 否 | 更新/增加完成状态 |
| `tool.failed` | `activity(kind=tool,status=failed)` | 否 | 显示安全错误文案 |
| `tool.cancelled` | `activity(kind=tool,status=cancelled)` | 否 | 显示已取消 |
| `artifact.created` | `artifact` | 否 | 暂存，不做 Citation UI |
| `answer.delta` | `answer_delta` | 是 | 累积回答 |
| `run.completed` | `done(status=completed)` | 否 | 完成消息 |
| `run.cancelled` | `done(status=stopped)` | 否 | 停止消息 |
| `run.failed` | `error`/终态 | 否 | 失败消息 |
| `run.timed_out` | `error`/终态 | 否 | 超时消息 |

未知事件不得降级为正文。可以忽略或记录开发日志，但不能转换成 `answer_delta`。

## 6. 安全投影规则

`activity` 是产品展示事件，不是 Python 原始事件的透传通道。Go 必须使用白名单构造
输出，只允许以下字段：

- `sequence`
- `kind`
- `status`
- 产品化 `label`
- 经过校验的稳定 Tool 名称
- `duration_ms`

禁止发送：

- Tool 完整输入参数；
- Tool 完整返回结果；
- Prompt 或 System Prompt；
- 模型隐式思维链；
- API Key、Cookie、Token；
- 数据库连接串；
- 未脱敏异常堆栈；
- 用户无权查看的外部资源内容。

Tool 展示名称由服务端做小型白名单映射，例如：

```text
tavily_search → 联网检索
fortune_chart → 命盘计算
未知 Tool     → 工具执行
```

不得依赖前端通过字符串替换猜测 Tool 的产品名称。若当前没有统一 Tool Display
Registry，本次只实现局部纯函数，后续再迁入 Registry。

## 7. Go 修改方案

### 7.1 提取纯投影函数

不要继续在 `streamV1` 的大型 `switch` 中手写多个任意 JSON。建议在
`go-backend/internal/httpapi` 内新增一个小型、无 I/O 的投影函数，例如：

```go
func projectBrowserEvent(event agent.Event) (payload any, visible bool)
```

职责：

- 解析经过验证的 `event.Data`；
- 按白名单映射成 `activity/answer_delta/artifact`；
- 保留 `event.Sequence`；
- 不修改 Product Run 状态；
- 不写数据库；
- 不把未知事件变成正文。

终态仍由现有 `streamV1` 状态机处理，避免这次顺手重构取消和完成逻辑。

### 7.2 修改 V1 SSE 投影

在 `go-backend/internal/httpapi/conversations.go` 中：

- 删除 `progress → delta`；
- 删除 `tool.completed → delta("已完成工具：...")`；
- `answer.delta` 改为浏览器 `answer_delta`；
- activity 事件写入 SSE 后立即 flush；
- `answer` builder 仍然且只能在 `answer.delta` 分支写入；
- `finishGeneration` 仍只收到 `answer.String()`；
- 不改变 event persistence、sequence gap recovery、cancel-wins 或 terminal handling。

### 7.3 Artifact 边界

`artifact.created` 可以投影成独立 `artifact` 事件，但本次只传递安全引用元数据：

- `artifact_id`
- `artifact_type`
- `content_hash`
- `mime_type`
- `size_bytes`

不要发送 Artifact 完整内容，不实现 Citation UI，也不把 Artifact 序列化到正文。

### 7.4 Legacy 兼容

生产配置仍可能为 `AGENT_PROTOCOL_MODE=legacy`。因此：

- 不要求本次重写 Python legacy adapter；
- 前端必须继续识别旧 `delta`；
- `delta.isThinking === true` 时转换为前端 activity，绝不进入正文；
- `delta.isThinking !== true` 时才作为 legacy answer delta 累积；
- V1 Go 链路不再产生 `delta`，只产生 `answer_delta/activity`。

迁移完成后，`delta` 在 TypeScript 中要有清楚的 deprecated 注释，防止未来继续使用。

## 8. 前端修改方案

### 8.1 消息状态模型

在 `ChatContainer.tsx` 的页面 `Message` 类型中增加：

```ts
activities?: RuntimeActivity[];
```

正文和活动必须使用两个独立变量：

```ts
let accumulatedAnswer = "";
let accumulatedActivities: RuntimeActivity[] = [];
```

禁止继续使用一个 `accumulatedContent` 同时承载两类信息。

### 8.2 使用纯 reducer 处理流事件

建议新增：

```text
frontend/src/lib/conversation-stream-reducer.ts
```

纯函数输入：

- 当前 answer；
- 当前 activities；
- 一个 `ConversationStreamEvent`。

纯函数输出：

- 新 answer；
- 新 activities；
- 可选 terminal status。

规则：

1. `answer_delta`：只追加 `data` 到 answer；
2. `activity`：只更新 activities；
3. legacy `delta + isThinking=true`：转换为 progress activity；
4. legacy `delta + isThinking!=true`：追加到 answer；
5. `artifact`：不进入 answer；
6. 重复 activity 通过稳定 `id` 去重；
7. 如果同一次 Tool 调用未来提供稳定 invocation id，应原位更新 started → completed；
8. 当前事件没有 invocation id 时，按 sequence 保留多次真实调用，不能按 Tool 名称
   错误地合并五次调用为一次。

### 8.3 最小运行活动 UI

新增一个职责单一的组件，例如：

```text
frontend/src/components/chat/RuntimeActivityList.tsx
```

产品行为：

- 位于回答正文上方，但不属于 Markdown 正文；
- 默认显示一行摘要，例如“已完成 5 次工具调用”；
- 运行中可以展开，终态后默认折叠；
- 展开后按 sequence 展示活动；
- started/running/completed/failed/cancelled 有可辨识状态；
- 相同 Tool 的五次真实调用显示五条或五次计数，不能伪装成一次；
- 不展示 Raw JSON、Tool 输入输出和内部异常；
- 空活动列表不渲染占位；
- 活动区没有复制按钮；
- 消息复制按钮只复制 answer。

本次不追求复杂动画和完整视觉重构，保持与现有 ChatMessage 风格一致即可。

### 8.4 删除字符串猜测的依赖

`ChatMessage.tsx` 当前 `parseContent()` 会通过 `StepN:`、`【计划】` 等字符串猜测思考
过程。本次处理原则：

- 新 V1 activity 不再写入 content，因此不需要通过该函数识别；
- 为 legacy 历史消息可暂时保留 `parseContent()`，但必须标注 deprecated；
- 不得给 `parseContent()` 增加“已完成工具”正则；
- `RuntimeActivityList` 使用结构化 `activities` prop；
- 新消息的复制内容始终使用 answer，不包含 activities。

### 8.5 刷新一致性

本次 P0 的强制不变量是：

```text
实时 answer == 刷新后的 StoredMessage.content == 复制内容
```

当前历史消息 API 没有重建完整 activity 的产品接口时，刷新后允许暂不展示运行活动，
但不允许刷新前后的正文不同。不要为了持久化 Activity 在本次新增数据库 schema 或
第二套事件存储。

后续 Create/Attach 与历史 Run 详情页可以从已持久化 Agent Event 构建历史 Activity，
不属于本次范围。

## 9. 测试方案

### 9.1 先写失败测试

Grok 必须先写能复现当前问题的测试，再改实现。不得只通过肉眼截图证明。

### 9.2 Go 单元测试

为纯投影函数覆盖：

- `progress` 产生 `activity`；
- `tool.started/completed/failed/cancelled` 产生正确 activity；
- `answer.delta` 产生 `answer_delta`；
- `artifact.created` 不产生正文；
- 未知事件不产生正文；
- 原始 Tool 参数、返回内容和异常详情不进入浏览器 payload；
- sequence 保留；
- malformed data 安全失败，不 panic。

### 9.3 Go 集成测试

在 `conversation_integration_test.go` 增加一个 V1 流场景，上游依次发送：

```text
run.started
progress
tool.started
tool.completed
tool.started
tool.completed
answer.delta("第一段")
answer.delta("第二段")
artifact.created
run.completed
```

必须断言：

- 浏览器收到结构化 activity；
- 浏览器收到两个 `answer_delta`；
- 浏览器没有收到包含“已完成工具”的 answer/delta；
- 拼接 answer 精确等于“第一段第二段”；
- 数据库 assistant message content 精确等于“第一段第二段”；
- Tool 名、Progress、Artifact 不存在于 message content；
- Product Run 和 message 均进入 completed；
- sequence 顺序不被打乱。

再保留一个 legacy 场景，确保生产 legacy 配置没有被破坏。

### 9.4 前端单元测试

项目当前没有前端测试脚本。本次允许只引入最小的 `vitest`，不引入完整浏览器 E2E
框架。为 `conversation-stream-reducer.ts` 覆盖：

- activity 不改变 answer；
- answer_delta 只改变 answer；
- 五次 tool.completed 保留五次事件且 answer 为空；
- legacy thinking delta 进入 activity；
- legacy non-thinking delta 进入 answer；
- artifact 不进入 answer；
- 重复 activity id 去重；
- done/error 不把提示文案追加到 answer。

在 `package.json` 增加稳定的 `test` 或 `test:unit` 命令，并提交 lockfile。不得为了
测试更换 Vite、React、Tailwind 或现有构建体系。

### 9.5 必跑命令

Grok 应根据仓库实际环境执行等价命令：

```powershell
cd go-backend
go test ./...

cd ..\backend
python -m pytest

cd ..\frontend
npm run test -- --run
npm run lint
npm run build

cd ..
git diff --check
```

如果项目最终选择 `test:unit`，报告中应使用真实脚本名，不能照抄不存在的命令。

## 10. 人工页面验收

使用 V1 模式运行本地环境，完成一次普通 Chat 和一次 Research：

### 场景 A：普通回答

- 输入不需要工具的简单问题；
- 正文正常流式输出；
- Activity 为空或仅显示模型阶段；
- 刷新后正文不变；
- 复制内容与正文一致。

### 场景 B：Research 多次检索

- 输入会触发多次联网检索的问题；
- 工具执行显示在独立折叠区；
- 正文中没有“已完成工具：tavily_search”；
- 多次调用按真实次数展示；
- 工具失败时活动区显示失败，但不把内部错误写进正文；
- 回答完成后折叠区默认收起；
- 刷新后正文保持一致；
- 复制内容不包含工具记录。

### 场景 C：停止生成回归

- 在 Tool 或回答过程中点击停止；
- 保持已经修复的取消语义；
- 页面最终显示 stopped；
- 立即发送下一条消息成功；
- 本次事件分层不能让取消问题复发。

## 11. 实施提交顺序

建议拆成三个可审查提交，不要生成一个无法定位问题的大提交。

### Commit 1：协议与失败测试

建议标题：

```text
test(agent): define structured browser event projection
```

内容：

- Go 投影测试；
- Go 集成失败测试；
- 前端 reducer 与测试基线；
- 浏览器事件 TypeScript 类型。

### Commit 2：Go 结构化事件投影

建议标题：

```text
fix(agent): separate runtime activity from answer stream
```

内容：

- Go 纯投影函数；
- V1 SSE 使用 `activity/answer_delta/artifact`；
- 安全白名单；
- legacy 行为不变；
- 所有 Go 测试通过。

### Commit 3：前端消费与展示

建议标题：

```text
fix(chat): render runtime activity outside assistant content
```

内容：

- stream reducer；
- ChatContainer 分离 answer/activity；
- RuntimeActivityList；
- ChatMessage prop 与复制行为；
- frontend unit/lint/build；
- 迁移进度文档更新。

如果实施中发现 Commit 1 的测试必须跟极少量脚手架一起提交，可以调整边界，但仍需
保持“协议/Go/前端”三个可审查逻辑块。

## 12. Grok 执行约束

Grok 开始前必须：

1. `git fetch origin`；
2. 确认最新 `origin/main` 提交；
3. 确认工作树干净；若不干净，停止并报告，不得覆盖现有改动；
4. 从 `origin/main` 创建独立分支，例如
   `codex/p0-structured-agent-events`；
5. 阅读本方案和三份关联架构文档的相关章节；
6. 先定位最新代码，不能机械依赖本文行号。

Grok 实施时禁止：

- `git reset --hard`、强制 checkout 或删除用户文件；
- 输出 `.env`、API Key、数据库密码；
- 修改本地模型配置；
- 改 Research 搜索策略；
- 改 Agent Runtime Store；
- 顺手完成 Citation、Skill、统一模式；
- 以正则删除正文里的工具字符串；
- 让 Go 和前端建立第二套 V1 事件事实源；
- 为了通过测试降低现有断言或跳过失败测试；
- 未经人工验收直接合并 `main` 或推送生产配置。

## 13. 遇到以下情况必须暂停

Grok 发现以下任一情况时停止实施并报告，不得自行扩大架构范围：

- 最新 `origin/main` 与本文描述的事件链路已经显著不同；
- 修改需要新增或破坏数据库 schema；
- 需要改变 Python AgentEvent v1 的稳定字段；
- 需要重写取消、恢复或 Run Supervisor；
- legacy 兼容无法在不破坏生产默认配置的情况下维持；
- 发现 Tool 原始输入/输出已经被前端或消息表持久化；
- 测试显示实时 answer 与数据库 content 的差异来自另一条未知链路；
- 工作树包含来源不明的未提交改动。

报告应包含：证据文件、触发条件、已完成内容、未完成内容和最小建议，不得继续猜测式
修改。

## 14. Definition of Done

以下条件全部满足才算完成：

- Python 稳定事件没有被降级为回答日志；
- V1 浏览器协议明确区分 `activity/answer_delta/artifact/done/error`；
- 只有 `answer_delta` 进入 `assistant.content`；
- legacy 模式仍可生成回答，thinking delta 不进入正文；
- 工具活动拥有独立、可折叠的最小 UI；
- 五次真实工具调用可以显示五次，但正文零次出现工具日志；
- 实时正文、刷新正文、复制内容完全一致；
- Artifact 不进入正文；
- Activity payload 通过安全白名单，不泄露敏感数据或隐式思维链；
- 取消修复没有回归；
- Go 全量测试通过；
- Python 全量测试通过；
- 前端单元测试、lint、生产 build 通过；
- `git diff --check` 通过；
- Grok 提供变更文件清单、提交 SHA、测试结果和剩余 TODO；
- 人工只需做页面产品验收和最终代码合并决定。

## 15. Grok 最终交付格式

Grok 完成后必须按以下格式返回：

```markdown
## 实施结果
- 分支：
- 基线 main SHA：
- 最终 SHA：

## 修改内容
- Go：
- Frontend：
- Tests：
- Docs：

## 协议确认
- 哪些事件进入 activity：
- 哪些事件进入 answer：
- legacy 如何兼容：
- artifact 如何处理：

## 验证结果
- go test ./...：
- python -m pytest：
- frontend unit：
- frontend lint：
- frontend build：
- git diff --check：

## 页面验收
- 普通 Chat：
- Research：
- 停止后继续：
- 刷新一致性：
- 复制一致性：

## 未完成与风险
- 非本次范围 TODO：
- 已知风险：
- 是否建议进入人工审核：
```

## 16. 可直接交给 Grok 的执行指令

```text
请在 qidianAgent 仓库中严格实施
docs/architecture/agent-event-presentation-migration-plan.md。

先 fetch origin，并从最新 origin/main 创建独立分支
codex/p0-structured-agent-events。开始前检查 git status；若存在来源不明的未提交
改动，立即停止并报告，不要覆盖。

本次只处理 Agent 运行事件与回答正文分离。必须先补失败测试，再实现 Go 的结构化
浏览器事件投影和前端的 answer/activity 分离。V1 只允许 answer.delta 进入最终
assistant content；progress/tool/model/route 必须进入 activity；artifact 独立处理。
同时保留 legacy 兼容，legacy 的 isThinking=true delta 不得进入正文。

不要修改 Research 检索次数、Prompt、LangGraph Workflow、模型配置、Runtime
Store、取消状态机、Citation、Skill、统一模式或生产开关。不要通过正则删除正文
字符串伪装修复。

按文档完成 Go/Python/Frontend 全量验证，拆分可审查提交。不要合并 main，不要修改
生产配置。最后严格使用文档第 15 节格式汇报结果，等待人工审核。
```

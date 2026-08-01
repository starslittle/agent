# Agent Core 未来扩展候选

> 状态：候选设计，尚未形成产品或架构决策
>
> 记录时间：2026-07-30
>
> 当前约束：本文不属于秋招 MVP、现有业务轮次或 Task 的授权范围

## 0. 文档目的

本文记录统一 Agent Core 在当前 MVP 之后可能继续演进的方向，避免讨论结论丢失，
同时防止尚未确认的复杂度提前进入实现。

本文中的字段、接口和流程都是讨论草案：

- 不覆盖
  [`统一助手与 Skill 目标架构`](unified-agent-skill-architecture.md)；
- 不改变当前“一次 Run 最多选择一个主 Skill”的 MVP 约束；
- 不表示已经决定实现多 Skill、多 Agent、通用 ReAct 或 Eval 平台；
- 不允许执行者依据本文扩大任何现有 Task 的 `allowed_paths`、目标或验收范围；
- 进入实现前必须由用户确认价值、范围和业务轮次，再新增或修订 Task。

## 1. 当前稳定基线

当前目标形态是：

```text
Root Assistant
→ Direct Answer，或最多一个主 Skill
→ Skill 内受控 Workflow / Capability
→ Answer、Artifact 或 Proposal
→ 用户确认后才更新产品事实
```

“最多一个主 Skill”不等于每次必须使用 Skill：

```text
普通聊天、改写、总结
→ Direct Answer
→ primary_skill = null

需要外部证据
→ Research

需要专业分析
→ 一个主 Skill
```

Root Assistant 负责意图理解、受控路由、风险和执行策略判断；它不承担 Fortune、
Decision 等专业业务逻辑，也不直接写 Wiki。

## 2. 候选一：统一 ExecutionPlan 抽象

未来可以考虑让 Root Assistant 先产生内部 `ExecutionPlan`，再由执行器运行。第一版
即使只有单 Skill，也可以表达为：

```json
{
  "plan_version": 1,
  "strategy": "single",
  "execution_mode": "skill",
  "primary_skill": "decision",
  "invocations": [
    {
      "invocation_id": "decision_1",
      "skill": "decision",
      "depends_on": []
    }
  ],
  "aggregation_policy": "primary_skill"
}
```

候选配套类型：

- `ExecutionPlan`：执行方式、依赖和汇总策略；
- `SkillInvocation`：一次 Skill 调用及其输入、预算、上下文和状态；
- `SkillResult`：回答、Artifact、Citation、Proposal、Usage 和公开摘要；
- `ExecutionPolicy`：`direct`、`workflow` 或 `bounded_action`。

是否在 MVP 内提前建立这些抽象尚未决定。只有当它们能减少后续迁移成本，且不会形成
空洞的通用框架时，才应进入当前实现。

## 3. 候选二：一个主 Skill 使用支持能力

复杂请求可能仍然只有一个业务主 Skill，但需要公共支持能力：

```text
Decision 主 Skill
├── 个人 Context
├── Research 证据
├── 确定性 Capability
└── Proposal
```

例如：

```text
“结合我的面试经历和最近岗位趋势分析两个 Offer”
→ primary_skill = decision
→ 支持能力 = personal_context + research
```

这不一定属于多 Skill 编排。候选实现方式包括：

1. 将 Research 作为主 Skill 可调用的受控 Subworkflow；
2. 将证据检索抽成公共 Capability；
3. 由上层 ExecutionPlan 先生成 Evidence Artifact，再交给主 Skill。

三种方式的数据所有权、预算、Citation、失败恢复和复用成本不同，目前不提前选型。

## 4. 候选三：多 Skill 串行或并行编排

只有单 Skill 无法表达、或用户明确要求多个独立专业视角时，才考虑
`MultiSkillPlan`。

串行示例：

```text
Research
→ Evidence Artifact
→ Decision
→ Decision Draft
```

并行示例：

```text
用户明确要求多个视角
→ Decision 与 Fortune 分别分析
→ Aggregator 保留共同点、冲突和不确定性
```

正式支持前至少需要：

- `Product Run → Skill Invocation` 父子关系；
- Skill 输入输出和 Artifact 的强类型契约；
- 依赖 DAG、并发上限和总预算；
- 分支级超时、取消、重试和失败策略；
- Context 与 Capability 隔离；
- 结果冲突和部分成功的产品表达；
- 写操作串行化和 Human-in-the-loop；
- 每个分支的 provenance、Usage 和观测。

默认不考虑自由 Swarm、Agent 群聊或模型任意创建 Skill。并行只能降低等待时间，不能
降低各 Skill Token 之和，还会增加规划和汇总成本。

## 5. 候选四：复用的 Bounded Action Loop

当前 Research 已经具有计划、检索、观察、证据评估和预算内补充检索的受控循环。
未来 Browser、Computer Use、Coding 或开放任务 Skill 可能需要复用的行动内核：

```text
Context
→ 产生结构化 NextAction
→ Capability、Schema、权限、风险和预算校验
→ 执行
→ 结构化 Observation
→ Checkpoint
→ 继续或结束
```

候选动作只允许来自封闭集合：

```text
final_answer
call_capability
request_user_input
require_approval
fail
defer
```

该循环不保存或展示模型隐藏思维链，只记录公开原因码、动作、Observation、Artifact
和 provenance。

当前不建立独立 `generic_react_v1`。只有第一个真实开放式 Skill 出现，并证明多个
Skill 确实需要相同循环时，才从已有 Workflow 中抽取。

## 6. 候选五：Run 内持久 Human-in-the-loop

当前 Proposal 可以让 Run 完成后由用户确认，再由 Go 写入业务事实。未来高风险工具
或长任务可能需要在同一个执行中暂停：

```text
running
→ approval_required / input_required
→ 持久化 Checkpoint
→ 用户批准、拒绝或补充输入
→ resume
```

是否引入该协议取决于是否出现必须保持同一执行身份的真实业务。普通澄清、下一轮
对话和 Run 完成后的 Proposal 不应为了形式统一而强行改成持久暂停。

## 7. 候选六：高级个人上下文规划

当前 Context Package 以确定性过滤和最小预算为主。未来可以评估：

- Direct Answer 是否按需读取少量个人上下文；
- 主 Skill 如何声明上下文类型、领域和时效要求；
- 外部证据与个人事实如何分别引用；
- 冲突、过期和不确定信息如何进入执行计划；
- 是否需要 Query Rewrite、向量召回或分层摘要。

任何升级仍需遵守：

- Go 是个人事实源；
- Python 不直接读取 Wiki 表；
- 默认不发送整个 Wiki；
- 历史 Run 冻结实际使用的 Revision；
- 被拒绝、过期、遗忘或未授权信息不进入默认上下文。

## 8. 候选七：Eval 与持续治理

Eval 治理不阻塞当前秋招 MVP，后续可单独形成业务轮次或 Quality Gate：

- Direct/Research/Skill 路由准确率；
- Skill 输入输出契约和失败分类；
- Tool/Capability 轨迹评估；
- 无效循环、预算耗尽和过早结束检测；
- Citation、Context 引用和 Proposal 安全性；
- Bad Case 收集、回放和回归集；
- Prompt、模型、Skill 版本对比；
- Judge 与人工复核的一致性。

运行时 Schema 校验、Capability 白名单、权限、预算、超时、取消和用户确认不属于
“可以延后的 Eval”，仍是当前系统安全边界。

## 9. 已确认方向：Agent 文档工作区

Agent 创建、读取、修改和删除 Document 是已确认的产品目标，不再讨论“是否需要”；
尚未确定的是实现轮次和完整协议。

预期能力边界：

- `document_create/read/update/delete` 进入受控 Capability Registry；
- 创建和修改通过 Revision 与 Changeset 保留版本、差异和审计；
- Agent 主动建议的修改先形成 Proposal/Changeset，由用户确认后执行；
- 永久删除只接受用户明确要求，并在执行前再次确认唯一目标和不可恢复范围；
- `document_hide/document_unhide` 不提供给 Agent，暂时隐藏和恢复只允许用户手动；
- Document CRUD 不得绕过 Wiki Proposal、Context 授权或其他长期记忆规则。

当前 TASK-017 仍只负责用户手动导入单篇 Markdown 或包含嵌套目录的文件夹。正式实现
Agent Document CRUD 前，需要新增独立 Task 或业务轮次，并冻结 Capability Schema、
Revision/Changeset、确认协议、失败恢复、权限审计和产品 E2E。

## 10. 进入实施前的决策门禁

每个候选进入实现前必须回答：

1. 哪个真实用户问题无法由当前单 Skill 或受控 Workflow 解决？
2. 用户是否能理解新增等待、成本、确认和部分失败？
3. 是否有至少一个可重复的产品验收旅程？
4. 是否能为新增状态定义恢复、取消、回滚和观测？
5. 是否需要新的数据模型，能否保持 Expand–Migrate–Contract？
6. 相比继续使用固定 Workflow，动态编排带来了什么可测价值？
7. 是否已经新增独立 Task、业务轮次、能力开关和停止条件？

没有通过这些门禁时，候选继续保留在本文，不进入 Backlog 执行图。

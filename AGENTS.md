# Repository Agent Rules

本文件适用于所有在本仓库内工作的编码 Agent。

## 0. 执行模式

执行任何规划、实现、修复或验收工作前，必须先读取
`collaboration/ACTIVE_MODE.yaml`，再读取其中 `protocol` 指向的模式协议。

- `mode: solo`：执行 `collaboration/solo/PROTOCOL.md`。该协议覆盖本文件和
  `collaboration/PROTOCOL.md` 中关于执行者、逐 Task Handoff、独立 Reviewer、
  分支/worktree、Task 验收节奏和 `codex_e2e` 执行时机的规定；Solo 模式不做
  逐 Task 产品 E2E，统一在全部 Round Task 完成后执行一次 Round 全量 E2E；
- `mode: codex-grok`：执行现有 `collaboration/PROTOCOL.md`，继续使用 Codex/Grok
  文件化协作模式；
- 模式协议只覆盖执行流程，不得覆盖产品范围、架构边界、数据所有权、安全规则、
  Task 的目标/非目标、`allowed_paths`、`forbidden_paths` 和用户授权边界；
- 只有用户可以授权切换模式。模式只能在 Task 边界切换，进行中的 Task 必须先完成、
  回滚或明确标记为阻塞；
- 无法读取模式文件、模式值未知或协议路径不存在时，停止实现并报告，不能自行猜测。

## 1. 文档事实优先级

执行任务前按以下顺序理解项目：

1. 用户在当前任务中的最新明确决定；
2. `docs/product/recruiting-mvp.md`：当前交付范围；
3. `docs/product/web-mvp.md`：完整 Web MVP；
4. `docs/product/future-product.md`：长期产品蓝图；
5. `docs/architecture/unified-agent-skill-architecture.md`：统一助手与 Skill 目标架构；
6. `docs/architecture/unified-agent-skill-migration-plan.md`：迁移实施顺序、历史 TODO
   追溯和阶段门禁；
7. `docs/architecture/agent-runtime.md`：现有 Runtime 基线；
8. `docs/decisions/`：已接受的架构决策；
9. `collaboration/rounds/`：当前业务交付轮次、完整验收和回滚边界；
10. `collaboration/tasks/`：单次执行范围和验收契约。

任务文件可以收窄范围，不能静默推翻更高层文档。发现冲突时停止扩大实现，并按当前
模式协议记录或报告冲突。

## 2. 协作角色（Codex/Grok 模式）

本节在 `mode: solo` 时由 Solo Protocol 完整替代。

- Codex 负责产品/架构方案、ADR、任务契约、独立代码审查，以及最终产品级 E2E
  验收；涉及真实页面和桌面交互时，由 Codex 使用 Browser / Computer Use 执行。
- Grok 是默认实现执行者，负责按已就绪 Task 修改代码、静态检查、单元测试、模块级
  集成测试和提交 handoff。
- 用户负责产品优先级、重大取舍、生产操作和最终接受。

执行者不能自行改变产品语义、数据所有权、状态机、外部 API 或生产门禁。
Grok 提供的自动化测试结果是交付证据，不能替代 Codex 的独立审查和必要的产品级
E2E，也不能自行把 Task 标记为 `accepted`。

## 3. Task 执行规则（Codex/Grok 模式）

本节关于状态、执行者、Handoff、Review 和逐 Task E2E 的规定在 `mode: solo` 时由
Solo Protocol 替代；Task 的产品和代码边界仍然有效。

1. 只执行 `status: ready` 且 `executor` 与自身匹配的 Task。
2. Task 所属 `business_round` 还必须已经获得用户授权并处于 `ready` 或
   `in_progress`；不得因为当前 Task 或本轮完成而自动进入下一业务轮次。
3. 开始前读取本文件、所属 Round、Task 引用的文档和直接相关代码。
4. 核对 Task 的 `base_commit`。仓库已前进时，先判断变更是否影响 Task；存在冲突则
   报告，不自行重写任务。
5. 核对 `source_todos`，理解本 Task 完整解决还是部分承接历史 TODO；不得静默把
   未覆盖部分标记为完成。
6. 严格遵守 `allowed_paths`、`forbidden_paths`、目标、非目标和验收标准。
7. 一次只执行一个需要 review gate 的 Task。
8. 完成后写入 `collaboration/handoffs/<task-id>-round-N.md`，然后停止等待审查。
9. 不直接修改 Round、Task、Review 文件或已接受的 ADR。
10. 审查意见只通过对应 Review 文件进入下一轮修复。

### 前端页面强制 Skills

任何创建或修改前端页面、视觉组件、布局或用户交互的 Task，必须在 Task
`required_skills` 中同时声明：

```yaml
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
```

执行者在修改前端代码前必须读取并使用这三个 Skill 的完整指令，并在 Handoff 中
记录它们如何影响信息架构、交互、视觉和可访问性。缺少或无法读取任意一个 Skill
时，Task 状态为 `blocked`；不得静默跳过、凭名称猜测内容或用普通提示词冒充。

## 4. 代码与数据边界

- Go 是用户、会话、消息、Product Run、个人 Wiki、决策、复盘和用户确认的事实源。
- Python 是 Agent Runtime、Skill Workflow、模型与 Capability 执行面。
- Python 不直接写 Go 拥有的产品业务表。
- LangGraph 是 Python 内唯一工作流编排引擎。
- 专业能力通过 Skill 接入；确定性原子动作通过 Capability 接入。
- 不建立第二套 Root Graph、Run Coordinator、模型 Gateway 或工具执行路径。
- AI 分析不能静默升级为用户确认事实。
- 命理叙事不能自动写入长期记忆，也不能作为确定性现实预测。

## 5. 变更安全

- 保留所有与当前 Task 无关的已有修改。
- 不使用破坏性 Git 命令，不重写他人的提交。
- 不提交 `.env`、Key、Cookie、连接串、用户内容或未脱敏日志。
- 数据库 Migration、删除兼容协议、写操作 Capability 和生产配置变更必须在 Task
  中显式授权。
- 业务能力关闭必须由服务端强制执行；前端隐藏不能代替权限或安全边界。
- Schema 迁移默认使用 Expand–Migrate–Contract。常规回滚关闭行为并保留数据，
  不执行破坏性 Down Migration，不删除已确认用户数据。
- 不在顺手修复中扩大依赖升级、格式化或目录重构范围。

## 6. 验证与交付（Codex/Grok 模式）

本节在 `mode: solo` 时由 Solo Protocol 的“每 Task 最小代码验证 + Round 唯一一次
全量产品 E2E”替代。

- Grok 负责代码层验证：静态检查、单元测试、模块级集成测试，以及 Task 明确要求由
  执行者运行的命令。
- Codex 负责验收层验证：检查真实 diff、架构契约和回归风险；对用户可见或跨服务
  Task，必须独立执行产品级 E2E。涉及真实页面或桌面应用时，优先使用 Browser /
  Computer Use 模拟完整用户操作。
- 纯内部、尚未接入产品路径的基础 Task 可以将 `codex_e2e` 标记为
  `not_applicable`，但必须在 Task 和 Review 中写明原因，仍需 Codex 独立审查。
- 无法运行测试时必须说明原因，不能把“未运行”写成“通过”。
- Handoff 必须包含基准提交、最终提交或工作树状态、修改文件、行为变化、验证结果、
  未完成事项、偏差和风险。
- Reviewer 以 Task 验收标准为准，输出 `accepted`、`changes_requested` 或
  `blocked_on_product_decision`。
- 只有 Codex 完成规定的独立审查，并通过必需的产品级 E2E 或确认其确实不适用后，
  才能输出 `accepted`。
- 每个 Task 完成后立即进入 Handoff、Review 和必要的最小 E2E；依赖 Task 只有在
  上游 `accepted` 后才能进入 `ready`，不等待所有 Task 完成后再一次性验收。
- 每个业务轮次结束后执行跨 Task 回归；完整秋招 MVP 12 步链路统一在 TASK-024 验收，
  避免每个小 Task 重复执行全量产品 E2E。
- 每个业务轮次的 Task 全部接受后，Codex 还必须完成 Round 文件规定的完整 E2E、
  上轮回归和非生产回滚/重新启用演练；未完成时该轮不能 `accepted`。
- 业务轮次 `accepted` 后停止，等待用户是否授权下一轮。它不等于生产发布获批。

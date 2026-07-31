# GPT / Codex Solo 执行协议

## 1. 目的与优先级

本模式用于由同一个 GPT/Codex 完成规划理解、代码实现、验证和产品 E2E，减少跨模型
交接、重复 Review、重复测试和长篇验收文档产生的 Token。

当前固定使用 `minimum-token` Profile：

```text
每 Task：实现 + 一次最小代码验证 + Commit + 短 LOG
整个 Round：全部 Task 完成后执行一次全量产品 E2E
```

模式入口是 `collaboration/ACTIVE_MODE.yaml`。当其中 `mode: solo` 时，本文件覆盖：

- Task 中历史遗留的 `executor: grok`；
- “Grok 必须验证”等执行者名称；
- 每 Task 独立 worktree；
- 逐 Task Handoff 和独立 Review 文件；
- 同一 Round 内逐 Task 请求用户授权；
- Task 中的 `codex_e2e: required` 和逐 Task 产品 E2E 要求；这些场景统一并入 Round
  结束时的一次全量产品 E2E。

它不覆盖产品、架构、数据、安全、路径和用户授权边界。当前 Task 文档仍是实现需求
权威来源；`collaboration/PROTOCOL.md` 和历史 Handoff/Review 保留为双模型模式与
历史证据，在 Solo 模式下不作为当前执行步骤。

## 2. 最小读取集

开始或恢复工作时只需要优先读取：

1. 根目录 `AGENTS.md`；
2. `collaboration/ACTIVE_MODE.yaml`；
3. 本协议；
4. `collaboration/solo/STATE.md`；
5. 当前 Round；
6. 当前 Task；
7. 当前 Task 直接相关代码。

仅在 Task 契约不完整、发生冲突或实现确实需要时，继续读取 Task 引用的产品、架构和
ADR 章节。不得为“确保了解”而每个 Task 重新加载全部文档、历史 Handoff 和 Review。

## 3. 授权与连续执行

- 用户按 Business Round 授权，不按 Task 重复授权；
- Round 已授权且 `STATE.md` 为 `running` 后，Codex 可以按依赖顺序连续完成本 Round
  的 Task；
- 每个 Task 完成后不等待新的用户确认，直接进入本 Round 下一个可执行 Task；
- Round 结束后停止，等待用户决定是否进入下一 Round；
- 生产操作、破坏性删除、不可逆 Migration、产品语义变化和超出 Round 的范围始终
  需要用户另行明确授权。

`STATE.md` 为 `paused` 时不得因为 Round 历史上曾获授权而自动开始；必须得到用户
明确的“开始/继续 Solo 执行”指令后才能改为 `running`。

## 4. 分支与提交

- 一个 Business Round 只使用一个 `codex/<round-id>-solo` 分支；
- 推荐为该 Round 创建一个仓库外部的同级 worktree，整个 Round 复用；
- 默认禁止创建 `codex/TASK-*` 分支，也不为每个 Task 重建 worktree；
- 每个 Task 至少形成一个边界清楚的代码提交，提交信息必须包含 Task ID，修复可以
  追加提交；
- 提交不得混入其他 Task 或用户的无关修改；
- Task 提交是局部回退单位，Round 是完整验收和合并单位；
- Round 全量 E2E 只在 Round 分支上执行，所有 Task 和 Round 验收完成后统一合并
  `main` 一次；
- 未经用户明确要求，不 Push、合并、部署或执行生产操作。

示例：

```text
main
└── codex/round-01-solo
    ├── TASK-004 commit
    ├── TASK-005 commit
    ├── TASK-006 commit
    ├── TASK-007 commit
    └── Round E2E fix commit（仅在需要时）
```

只在以下情况允许临时 Task 子分支，并在短 LOG 中说明原因：

- 多个 Agent 获得明确授权并行执行；
- 高风险 Migration 或互斥方案需要隔离试验；
- 紧急修复必须插入当前 Round；
- 当前 Task 的失败会阻塞但不应污染 Round 分支。

没有这些条件时，创建 Task 分支属于不必要的流程和 Token 开销。

## 5. 单个 Task 流程

```text
读取当前 Task 与相关代码
→ 核对依赖、范围和工作树
→ 实现
→ 运行一次最小代码验证
→ 检查真实 diff
→ 提交代码
→ 更新 STATE 与短 LOG
→ 进入同一 Round 下一个 Task
```

Solo 模式不创建逐 Task Handoff 和 Review。实现中发现的问题直接在当前 Task 内修复，
不通过 `round-2/3/4` 文档往返。

Task 完成只表示“代码实现和最小代码验证完成”，不单独进入产品验收。Codex 不在
Task 之间切换成 Reviewer 身份，不生成验收结论，不等待复验，也不请求用户确认。

Task 的功能目标、非目标、输入输出契约、验收标准、必需 Skills、允许和禁止路径仍然
有效。Task 中纯粹用于双模型交接的执行者名称、Handoff 路径、独立 Reviewer 和重复
E2E 要求由本协议替代。

## 6. 每 Task 最小代码验证

- 优先运行当前修改模块的格式、类型、单元和必要集成测试；
- 每项验证默认只执行一次；实现过程中已经获得可信通过结果时，提交前不重复运行；
- 成功时只保留命令和摘要，避免读取或记录大段日志；
- 失败时才展开相关错误，并在同一 Task 内修复后重跑失败范围；
- 不由第二个角色重复执行已经通过且没有独立价值的同一命令；
- Task 阶段不启动项目做产品 Smoke，不使用 Browser / Computer Use，不执行 Task
  产品 E2E；
- Task 文档中的 `codex_e2e: required` 仅用于收集 Round E2E 覆盖项，不触发逐 Task
  E2E；
- Browser / Computer Use、跨 Task 回归和回滚演练只在全部 Round Task 完成后统一
  执行；
- 数据库、权限、状态机、幂等、恢复、用户数据写入/删除等高风险 Task，仍须运行其
  正确性所必需的代码级集成测试，但这不构成产品 E2E。

涉及前端页面、视觉、布局或交互时，继续遵守根 `AGENTS.md` 规定的三个前端 Skill
门禁；只在真正涉及前端的 Task 加载，不扩散到纯后端 Task。Skill 对实现的影响只需
在短 LOG 中用一句话记录，不创建 Handoff。

## 7. 状态与记录

Solo Task 只使用：

```text
pending → running → completed | blocked
```

当前进度以 `collaboration/solo/STATE.md` 为准。原 Task 文件中的 `draft/ready` 和
`executor` 保留给历史及 Codex/Grok 模式，不要求 Solo 每次同步。

`completed` 只表示实现完成，不表示该 Task 已单独完成产品验收；产品结论由 Round
全量 E2E 一次性给出。

`collaboration/solo/LOG.md` 每个 Task 只记录：

- Task ID；
- commit；
- 一句话结果；
- 实际验证命令与结果；
- 未解决风险或“无”。

禁止复制测试长日志、模型思维链、完整 diff 或大段历史背景。

## 8. Round 验收

本 Round 所有 Task `completed` 后，才执行本 Round 唯一一次完整产品验收：

1. 运行 Round 定义的完整用户旅程；
2. 执行必要的全仓或跨服务回归；
3. 使用 Browser / Computer Use 完成规定的产品 E2E；
4. 验证能力关闭、局部回滚和重新启用；
5. 将结果简要写入 `LOG.md`；
6. 把 `STATE.md` 改为 `acceptance` 或 `accepted`；
7. 停止并等待用户授权下一 Round。

不会为各 Task 拆分或预演这套 E2E。若 Round 全量 E2E 发现问题，回到对应 Task 修复
并新增提交，只复验失败场景及受修复影响的必要回归；不补建双模型 Handoff/Review
链，也不无条件重跑全部已通过场景。

## 9. 必须暂停

出现以下任一情况必须把状态改为 `blocked` 或保持 `paused` 并询问用户：

- 产品语义存在会改变实现方向的歧义；
- 需要越过 `allowed_paths` 或触碰 `forbidden_paths`；
- 需要破坏性数据操作、生产修改或新权限；
- 发现不属于当前 Task 的用户修改且无法安全绕开；
- 必需 Skill、依赖、测试环境或凭据不可用；
- 关键验证无法运行或失败原因无法在当前范围内解决；
- 当前模式文件、状态文件或 Task 依赖关系不一致。

## 10. 切回 Codex/Grok

只能在 Task 边界由用户授权切换。切换时：

1. 将 `ACTIVE_MODE.yaml` 改为 `codex-grok`，协议指向
   `collaboration/PROTOCOL.md`；
2. 把 Solo 已完成 Task、commit 和遗留风险同步回 Backlog/Task；
3. 新 Task 重新按 Codex/Grok 协议冻结 `executor`、`base_commit`、Handoff 和
   Review Gate；
4. 不改写既有 Solo `LOG.md` 历史。

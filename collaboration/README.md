# Agent 执行与协作区

本目录是启点的文件化任务交接层。

它不保存第二份产品或架构文档。长期事实位于 `docs/`；本目录只保存执行协议、任务、
实现交接和审查结果。

## 当前模式

执行前必须读取 [`ACTIVE_MODE.yaml`](ACTIVE_MODE.yaml)：

- `solo`：使用 [`solo/PROTOCOL.md`](solo/PROTOCOL.md)，由 GPT/Codex 连续实现，
  每 Task 只做实现、一次最小代码验证、Commit 和短 LOG；全部 Task 完成后只执行
  一次 Round 全量产品 E2E；默认一个 Round 一个分支/worktree，每个 Task 只形成
  独立 Commit；
- `codex-grok`：使用 [`PROTOCOL.md`](PROTOCOL.md)，恢复 Codex/Grok 分工、Handoff
  和独立 Review。

当前启用 `solo`，但状态为 `paused`，尚未启动 TASK-004。原 Codex/Grok 内容和历史
记录完整保留，可在 Task 边界经用户授权后切回。

## Codex/Grok 模式角色

- Codex：Planner / Architect / Reviewer / Product E2E Owner
- Grok：Executor / Unit & Module Test Owner
- 用户：Product Owner / Final Approver

## 目录

```text
collaboration/
├── ACTIVE_MODE.yaml
├── README.md
├── PROTOCOL.md
├── solo/
├── templates/
├── rounds/
├── tasks/
├── handoffs/
└── reviews/
```

## Codex/Grok 模式基本流程

1. Codex 在 [`rounds/`](rounds/README.md) 维护业务轮次，在
   [`tasks/BACKLOG.md`](tasks/BACKLOG.md) 维护 Task 依赖。
2. 用户一次只授权一个业务轮次；架构、轮次验收、回滚边界和基准冻结后才允许首个
   Task 进入 `ready`。
3. Grok读取 `AGENTS.md`、所属 Round、Task和Task引用的文档。
4. Grok只修改允许范围内的代码和测试，完成静态检查、单元测试和模块级集成测试。
5. Grok写入对应Handoff并停止；其测试结果是交付证据，不等于最终验收。
6. Codex检查Task、diff、测试和架构一致性。
7. 对用户可见或跨服务Task，Codex使用Browser / Computer Use执行真实产品E2E。
8. Codex将代码审查和E2E结果写入Review。
9. `changes_requested` 时，Grok只处理该Review。
10. Codex复验并写入 `accepted` 后，依赖任务才能开始。
11. 本轮全部 Task 接受后，Codex执行完整轮次 E2E、上轮回归和回滚演练。
12. 轮次接受后停止，等待用户是否授权下一轮。

本节只在 `mode: codex-grok` 时生效。详细状态和文件格式见
[PROTOCOL.md](PROTOCOL.md)。Solo 流程只读取 [Solo Protocol](solo/PROTOCOL.md)、
[Solo State](solo/STATE.md) 和 [Solo Log](solo/LOG.md)。

## 当前任务草案

- [完整迁移 Backlog：29 个 Task](tasks/BACKLOG.md)
- [2026-07-30 Backlog 全量审查](reviews/BACKLOG-REVIEW-2026-07-30.md)
- [业务交付轮次与局部回滚](rounds/README.md)
- [TASK-001：建立 Skill 契约基础](tasks/TASK-001-skill-contract.md)

当前 ROUND-02 已验收；ROUND-03 已按最新产品决定完成文档准备，但仍等待用户明确
授权开始。Solo 进度以 [Solo State](solo/STATE.md) 为准；原 Task/Review 状态保留给
历史和 Codex/Grok 模式。

# Codex / Grok 协作区

本目录是启点的文件化任务交接层。

它不保存第二份产品或架构文档。长期事实位于 `docs/`；本目录只保存执行协议、任务、
实现交接和审查结果。

## 角色

- Codex：Planner / Architect / Reviewer / Product E2E Owner
- Grok：Executor / Unit & Module Test Owner
- 用户：Product Owner / Final Approver

## 目录

```text
collaboration/
├── README.md
├── PROTOCOL.md
├── templates/
├── rounds/
├── tasks/
├── handoffs/
└── reviews/
```

## 基本流程

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

详细状态和文件格式见 [PROTOCOL.md](PROTOCOL.md)。

## 当前任务草案

- [完整迁移 Backlog：28 个 Task](tasks/BACKLOG.md)
- [2026-07-30 Backlog 全量审查](reviews/BACKLOG-REVIEW-2026-07-30.md)
- [业务交付轮次与局部回滚](rounds/README.md)
- [TASK-001：建立 Skill 契约基础](tasks/TASK-001-skill-contract.md)

全部 Task 和业务轮次当前保持 `draft`。形成 Git 基准提交、填写 `base_commit` 并
获得用户对当前轮次的明确授权后，才将轮到执行的单个 Task 改为 `ready`。

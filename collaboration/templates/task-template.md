---
id: TASK-000
title: 替换为任务标题
status: draft
executor: grok
base_commit: ""
business_round: ROUND-00
depends_on: []
source_todos: []
required_skills: []
risk: low
review_gate: required
codex_e2e: required
allowed_paths: []
forbidden_paths: []
---

# TASK-000：任务标题

## 目标

说明本Task完成后可以观察到的结果。

## 业务轮次

- 所属 Round：`ROUND-00`；
- 说明本 Task 对该轮业务结果、能力控制或回滚边界的贡献；
- Task `accepted` 只解除同一已授权 Round 内的下游依赖，不自动授权下一 Round。

## 架构依据

- `docs/...`
- `docs/decisions/...`

## 历史TODO追溯

- 列出 `source_todos` 对应的原始文档章节；
- 没有历史TODO的新产品需求，说明对应的产品文档来源；
- 说明本Task解决全部还是部分原始TODO，未覆盖内容由哪个后续Task负责。

## 必需Skills

前端页面、视觉组件、布局或交互Task必须声明并使用：

```text
frontend-design
ui-ux-pro-max
web-design-guidelines
```

其他Task写“无”。Skill不可用时必须阻塞，不能静默跳过。

## 当前事实

列出执行者不应重新猜测的代码或产品现状。

## 非目标

- 明确本轮不处理的事项。

## 输入与输出契约

说明类型、API、事件、数据库或文件契约。

## 实现约束

- 数据所有权；
- 兼容要求；
- 错误行为；
- 安全和隐私；
- 性能或预算。

## 验收标准

- [ ] 可验证条件一；
- [ ] 可验证条件二。

## Grok必须验证

```text
列出静态检查、单元测试、模块级集成测试或其他确定性命令
```

## Codex验收与E2E

- `codex_e2e: required` 时，描述需要Codex使用Browser / Computer Use验证的用户旅程、
  环境、预期结果和关键证据；
- `codex_e2e: not_applicable` 时，说明为什么本Task尚未形成可执行的产品路径，以及
  Codex应采用的替代审查证据。

## Handoff

写入：

```text
collaboration/handoffs/TASK-000-round-1.md
```

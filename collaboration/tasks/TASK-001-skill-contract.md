---
id: TASK-001
title: 建立 Skill Manifest 与 Registry 契约基础
status: draft
executor: grok
base_commit: pending-baseline-commit
business_round: ROUND-02
depends_on: []
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P1：下一轮产品架构迁移"
  - "docs/architecture/unified-agent-skill-architecture.md#Phase-1：Skill-契约基础"
risk: medium
review_gate: required
codex_e2e: not_applicable
allowed_paths:
  - backend/agent/skills/**
  - backend/configs/skills.yaml
  - backend/tests/unit/test_skill_*.py
  - backend/tests/fixtures/skill_*.json
  - collaboration/handoffs/TASK-001-*.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-001：建立 Skill Manifest 与 Registry 契约基础

## 目标

在Python Agent层新增独立、强类型、可启动校验的Skill契约，为后续
`requested_skill/resolved_skills`和统一助手路由提供基础。

本Task只建立定义和Registry，不接入当前请求链路，不改变Chat、Research或Fortune
现有行为。

## 架构依据

- `docs/product/recruiting-mvp.md`
- `docs/product/web-mvp.md`
- `docs/architecture/unified-agent-skill-architecture.md`
- `docs/architecture/agent-runtime.md`
- `docs/decisions/ADR-010-codex-grok-delivery-workspace.md`

## 历史TODO追溯

本Task部分承接：

- `Agent Runtime迁移状态 / P1`中的Skill Registry；
- `统一助手与Skill目标架构 / Phase 1`中的Skill Manifest与Skill Registry。

本Task不承接`requested_skill/resolved_skills`、兼容Adapter和Skill provenance，
这些内容在Product Run协议稳定后由后续Task完成。

## 当前事实

- 当前只有一个`AgentApplication`、一个Root Graph和一个`ExecutionRegistry`；
- `research_v1`和`fortune_v1`已经是受控Subgraph；
- Capability的权威定义在现有Capability/Tool Registry；
- `agents.yaml`当前仍是生产AgentSpec来源；
- 本Task不能建立第二套路由或执行实现；
- Direct Chat不是Skill。

## 非目标

- 不修改任何HTTP、SSE或Go/Python协议；
- 不增加`requested_skill`字段；
- 不修改`agents.yaml`；
- 不改变现有Agent别名；
- 不把现有请求切换到Skill Registry；
- 不修改任何Workflow或Prompt；
- 不实现Decision Skill；
- 不修改前端；
- 不增加数据库Migration。

## 交付内容

### 1. Skill Manifest

在`backend/agent/skills/`中定义强类型模型，至少包含：

- `id`
- `version`
- `title`
- `description`
- `workflow`
- `input_schema`
- `output_schema`
- `allowed_capabilities`
- `model_requirements`
- `budgets`
- `risk`
- `memory`
- `ui`
- `available`

字段必须禁止未知项，字符串和数值具有合理有限约束。

### 2. Skill配置

新增`backend/configs/skills.yaml`，只登记：

- `research`
- `fortune`

不得登记尚无Workflow的`decision`。

映射：

```text
research -> research_v1
fortune  -> fortune_v1
```

Capability必须与当前实际Registry一致，不使用架构文档中的示例旧名称。

### 3. Skill Registry

Registry至少提供：

- 按ID解析Skill；
- 列出available Skill；
- 生成稳定配置fingerprint；
- 校验ID唯一；
- 校验版本为正整数；
- 校验Workflow存在；
- 校验Capability存在；
- 校验模型要求字段有效；
- 校验模型调用、工具调用和 deadline 预算为有限正值；
- 校验不可用Skill不会进入available列表；
- 缺失配置和非法配置在构造阶段失败。

Registry不得：

- 调用模型；
- 调用Capability；
- 编译LangGraph；
- 读取Provider Key；
- 根据自然语言执行Skill路由；
- 修改全局`AgentCatalog`。

### 4. 单元测试

测试至少覆盖：

- 正常加载Research/Fortune；
- 稳定fingerprint；
- 重复ID失败；
- 未知Workflow失败；
- 未知Capability失败；
- 非法版本失败；
- 额外字段失败；
- unavailable Skill不出现在available列表；
- 配置文件不存在或内容非法时失败。

测试不能调用真实模型、网络、数据库或工具。

## 兼容约束

- 当前`agents.yaml`和`AgentCatalog`仍保持唯一运行行为；
- 新Skill Registry在本Task结束后可以尚未进入readiness；
- 现有测试行为必须不变；
- 后续Task负责协议字段、兼容Adapter和provenance。

## 验收标准

- [ ] Skill模型为强类型且`extra=forbid`；
- [ ] `skills.yaml`只包含Research和Fortune；
- [ ] Registry能在无外部依赖情况下加载和验证；
- [ ] Registry引用当前真实Workflow和Capability名称；
- [ ] Skill 预算和 deadline 由 Manifest 强类型校验，不在接入层复制；
- [ ] 没有出现第二套Root Graph、Runtime或工具执行器；
- [ ] 当前运行链没有行为变化；
- [ ] 新增测试覆盖成功和失败路径；
- [ ] 允许范围外没有代码修改。

## Codex验收与E2E

本Task只建立尚未接入Root Assistant、现有Workflow、API或前端的内部Skill契约，
因此`codex_e2e: not_applicable`。Codex仍需独立检查真实diff、公开类型契约、配置
加载行为和测试结果；后续接入真实产品调用链的Task必须单独声明并执行产品级E2E。

## Grok必须验证

从`backend/`执行：

```text
uv run pytest tests/unit/test_skill_*.py -q
uv run pytest tests/unit -q
uvx ruff check agent/skills tests/unit/test_skill_*.py
```

如果本地环境无法执行，Handoff必须记录具体原因和未验证项。

## Handoff

完成后写入：

```text
collaboration/handoffs/TASK-001-round-1.md
```

使用`collaboration/templates/handoff-template.md`，然后停止等待Codex Review。

## 发布条件

本Task当前为`draft`。只有以下条件完成后，Planner才可以将其改为`ready`：

- 当前产品文档、统一助手/Skill架构和协作协议已经形成一个Git基准提交；
- `base_commit`已经替换为该提交的完整SHA；
- Grok工作分支或worktree从该提交创建；
- ROUND-01 已经 `accepted`；
- 用户明确授权开始 ROUND-02。

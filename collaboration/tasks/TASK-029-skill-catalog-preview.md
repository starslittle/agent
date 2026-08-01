---
id: TASK-029
title: 建立 Skills 安全目录与只读详情
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-011
  - TASK-012
source_todos:
  - "docs/product/recruiting-mvp.md#7.4：Skills"
  - "docs/product/web-mvp.md#5.6：Skills"
  - "docs/decisions/ADR-014：Skills只读目录"
  - "docs/architecture/unified-agent-skill-architecture.md#6：Skill Manifest"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/skills/**
  - backend/app/api/**
  - backend/app/runtime/**
  - backend/configs/skills.yaml
  - backend/tests/**
  - go-backend/internal/agentclient/**
  - go-backend/internal/skills/**
  - go-backend/internal/httpapi/skill*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/httpapi/*skill*_test.go
  - frontend/src/components/workspace/**
  - frontend/src/features/skills/**
  - frontend/src/pages/**
  - frontend/src/lib/skill-api.ts
  - frontend/src/App.tsx
  - frontend/src/App.css
  - frontend/src/index.css
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-029-*.md
forbidden_paths:
  - backend/agent/prompts/**
  - backend/agent/workflows/**
  - backend/agent/tools/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-029：Skills 安全目录与只读详情

## 目标

增加 `Skills` 一级入口，让用户查看当前真实可用 Skill 的公开说明，并从详情进入统一
对话。Python Registry 仍是 Manifest 与执行可用性的事实源，Go 输出结合产品策略、
权限和 Runtime readiness 的用户安全投影，前端不再用静态常量充当可用性事实源。

## 公开投影

进入 `ready` 前冻结跨服务与浏览器 Schema。用户响应最多包含：

```text
id
version
title
description
command
public_purpose
public_capabilities[].label/description
context_scope[].label
confirmation_summary
may_propose_updates
available/effective（仅公开可理解状态）
```

不得返回：

- 系统 Prompt 或隐藏工作流指令；
- Workflow、输入输出内部 Schema、模型路由细节和预算；
- Secret、连接串、内部禁用原因；
- 原始工具输入输出或仅供内部观测的字段。

Capability 必须通过明确的公开文案白名单映射，不能把内部工具标识和参数 Schema 原样
倾倒给浏览器。未知字段默认不公开。

## 路由与交互

```text
/skills                 目录与搜索
/skills/:skillId        可深链接详情
/?skill=:skillId        回到对话并预选 Skill
```

- 目录只展示当前用户 effective 且 `ui.visible` 的 Skill；首版真实数据为 `research`、
  `fortune`，不得补假 Skill；
- 详情桌面端可用路由化 Dialog，移动端使用全屏页或 Sheet；刷新和浏览器后退正确；
- Dialog 有标题/描述、焦点圈定、Escape 关闭、关闭后焦点恢复和 overscroll containment；
- “在对话中使用”进入统一对话并预选 Skill，仍由服务端在创建 Run 时重新校验；
- 搜索、空状态、加载、错误和 unavailable 深链接有明确结果；
- `/` 菜单、Skill Chip、Runs 和 Skills 目录共用同一 API Adapter/类型，不保留第二份
  手写可用列表。

## 非目标

- 不实现 Skill 编辑、复制、Draft、测试、发布、版本回滚或市场；
- 不提供内置 Skill 开关、卸载或重命名；
- 不允许前端绕过服务端 effective capability；
- 不修改 Workflow、Prompt 或 Capability 执行行为。

## 验收标准

- [ ] Go/Python 契约只暴露字段白名单，未知字段失败关闭或被丢弃；
- [ ] 目录与 `/` 菜单只展示同一组真实 effective Skill；
- [ ] `research`、`fortune` 详情内容来自服务端，不依赖前端重复常量；
- [ ] 不存在 Prompt、隐藏 Workflow、Secret、原始工具数据泄露；
- [ ] 详情深链接、刷新、后退和关闭焦点恢复正确；
- [ ] “在对话中使用”预选 Skill，Run 创建仍执行服务端校验；
- [ ] unavailable/unknown 状态不泄露内部原因；
- [ ] 375、768、1024、1440px 无横向溢出，键盘和屏幕阅读器语义可用；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

契约测试必须注入带有隐藏 Prompt、未知字段和 unavailable Skill 的 fixture，证明浏览器
投影不泄露且 `/` 菜单不会漂移。

## Codex验收与E2E

使用 Browser / Computer Use 搜索并打开两个真实 Skill，验证深链接、刷新、后退、键盘
焦点、移动端详情、“在对话中使用”、不可用状态和网络失败；检查浏览器响应不含禁止
字段，并回归现有 `/` 选择、自动路由和 Agent Runs Skill 展示。

## Handoff

写入 `collaboration/handoffs/TASK-029-round-1.md` 后停止。

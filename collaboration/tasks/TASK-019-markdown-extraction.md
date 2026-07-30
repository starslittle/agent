---
id: TASK-019
title: 从 Markdown 提取候选信息并生成 Wiki Proposal
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-011
  - TASK-017
  - TASK-018
source_todos:
  - "docs/product/recruiting-mvp.md#8.2：Markdown Document流程"
  - "docs/product/recruiting-mvp.md#16：唯一验收链路步骤2-3"
  - "docs/architecture/unified-agent-skill-architecture.md#4：文件与产品控制面"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/documents/**
  - backend/agent/prompts/document_extract_*.txt
  - backend/app/api/agent_runs.py
  - backend/app/runtime/**
  - backend/tests/**
  - go-backend/internal/documents/**
  - go-backend/internal/proposals/**
  - go-backend/internal/conversation/**
  - go-backend/internal/httpapi/document*.go
  - go-backend/internal/httpapi/proposal*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/agent/**
  - go-backend/internal/agentclient/**
  - frontend/src/features/documents/**
  - frontend/src/features/wiki/**
  - frontend/src/lib/document-api.ts
  - collaboration/handoffs/TASK-019-*.md
forbidden_paths:
  - backend/agent/workflows/research_v1/**
  - backend/agent/workflows/fortune_v1/**
  - backend/agent/tools/**
  - backend/configs/skills.yaml
  - docker-compose.yml
---

# TASK-019：Markdown 候选信息提取

## 目标

对一篇已保存 Markdown 执行受控结构化提取，生成候选事实、当前状态、个人规则或
AI 分析 Proposal；不直接写入 Wiki。

## 执行形态

Markdown 解析、提取和冲突检查是内部运行步骤，不作为用户可选 Skill。它必须复用
现有 Agent Runtime、Model Gateway、结构化输出、事件和 Product Run，不建立第二套
任务系统。

该 Product Run 必须使用稳定 `run_purpose=document_extraction`（或进入 `ready` 前
冻结的等价枚举）并关联 `document_id`。重复触发按 document content hash、提取版本
和幂等键返回同一执行或明确新版本，不能产生不可控重复 Proposal。

提取结果至少包含：

- candidate type/domain/content；
- document ID 与位置/片段来源；
- confidence；
- proposed action：create/update；
- 可能冲突的 Wiki Item/Revision；
- 公开解释摘要；
- extraction/model/prompt 版本。

## 安全与质量

- 原文不是 confirmed fact；
- 模型输出经过强类型校验和有界修复；
- 每个 Proposal 可追溯到文档来源；
- 低置信度和冲突项明确标记；
- 不把文档中的指令当作系统指令执行；
- 不调用联网或无关 Capability；
- 不写 Wiki。

## 非目标

- 不批量处理；
- 不做向量索引；
- 不实现确认 UI；
- 不提取 Skill 更新建议；
- 不修改 Research/Fortune Workflow。

## 验收标准

- [ ] 一篇面试复盘可生成结构化 Proposal；
- [ ] 每项 Proposal 有来源和版本；
- [ ] Prompt injection 文本不会改变系统行为；
- [ ] 冲突和低置信度可见；
- [ ] 失败 Run 不写 confirmed Wiki；
- [ ] 重试不生成不可控重复 Proposal；
- [ ] Run 与 document、content hash、提取版本和产生的 Proposal 可追溯；
- [ ] Run 时间线显示真实提取步骤；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd backend && uv run pytest tests -q
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

使用固定 Markdown fixture，不依赖真实 Provider 完成契约测试。

## Codex验收与E2E

使用 Browser / Computer Use 导入面试复盘，触发提取，检查候选类型、来源、冲突、
失败、重试、Run 时间线以及 Wiki 尚未被直接修改。

## Handoff

写入 `collaboration/handoffs/TASK-019-round-1.md` 后停止。

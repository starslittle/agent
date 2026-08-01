---
id: TASK-024
title: 建立并通过秋招 MVP 唯一产品闭环 E2E
status: draft
executor: grok
base_commit: pending
business_round: ROUND-04
depends_on:
  - TASK-006
  - TASK-013
  - TASK-016
  - TASK-017
  - TASK-020
  - TASK-023
  - TASK-028
source_todos:
  - "docs/product/recruiting-mvp.md#16：唯一验收链路"
  - "docs/product/recruiting-mvp.md#17：秋招技术验收"
  - "docs/product/recruiting-mvp.md#18：配套交付"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/tests/**
  - go-backend/internal/**/*_test.go
  - frontend/src/**/*.test.*
  - scripts/**
  - docs/operations/recruiting-mvp-*.md
  - README.md
  - collaboration/handoffs/TASK-024-*.md
forbidden_paths:
  - backend/agent/workflows/**
  - backend/agent/prompts/**
  - frontend/src/components/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
---

# TASK-024：秋招 MVP 唯一产品闭环

## 目标

建立可重复的自动验收材料，并由 Codex 使用 Browser / Computer Use 独立通过产品
文档定义的唯一链路。

## 唯一链路

```text
1. 我的空间中的确认信息保存“正在准备 Agent 岗位秋招”
2. 导入包含面试复盘 Markdown 的求职文件夹
3. Agent 提取候选信息，用户确认
4. 询问“下一轮优先准备系统设计还是算法”
5. 自动选择 Decision Skill
6. 页面展示 Skill 和所用个人上下文
7. Agent 流式返回分析
8. Agent Run 展示真实执行步骤
9. Agent 生成“当前薄弱点”更新建议
10. 用户确认后 Wiki 更新
11. 用户保存最终选择
12. 下一次对话使用更新后的信息
```

## 交付内容

- 稳定、脱敏的演示 fixture；
- 可重复初始化或清理的测试用户数据方案；
- API/集成自动测试覆盖可自动部分；
- Computer Use 手工/半自动脚本；
- 失败场景清单；
- README、架构图、演示步骤和结果摘要；
- 真实未通过项，不用文档绕过。

## 非目标

- 不在验收 Task 中新增产品功能；
- 不借机重构业务代码；
- 不使用真实生产用户数据；
- 不要求真实外部 Provider 作为所有自动测试前提；
- 不进行生产切换。

## 验收标准

- [ ] 12 步唯一链路逐步有证据；
- [ ] 正常、取消、失败、刷新和重试不回归；
- [ ] Wiki 更新只在确认后发生；
- [ ] 下一次对话使用最新确认信息；
- [ ] Run、Skill、Context、Model 和 Capability 可追溯；
- [ ] 自动测试和 Computer Use 结果一致；
- [ ] 演示材料不泄露 Secret 或用户数据；
- [ ] 所有跳过项有明确原因和后续任务。

## Grok必须验证

运行当时仓库规定的完整 Python、Go、前端、数据库和容器门禁，并生成机器可读摘要。
Handoff 必须逐项标记唯一链路的自动覆盖情况。

## Codex验收与E2E

Codex 必须亲自使用 Browser / Computer Use 走完 12 步，并检查刷新、复制、Run
时间线、Proposal、历史 Revision 和下一轮 Context。只有实际产品链路通过才可
`accepted`。

## Handoff

写入 `collaboration/handoffs/TASK-024-round-1.md` 后停止。

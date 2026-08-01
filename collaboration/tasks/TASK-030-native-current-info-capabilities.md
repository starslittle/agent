---
id: TASK-030
title: 为统一助手增加轻量联网与时效信息能力
status: ready
executor: codex
base_commit: b425e69
business_round: ROUND-03
depends_on:
  - TASK-011
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#P2：质量、成本和体验优化"
  - "docs/architecture/unified-agent-skill-migration-plan.md#普通链路与深度思考链路的结合"
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - backend/agent/**
  - backend/configs/agents.yaml
  - backend/configs/skills.yaml
  - backend/tests/**
  - collaboration/tasks/TASK-030-native-current-info-capabilities.md
  - collaboration/tasks/BACKLOG.md
  - collaboration/rounds/ROUND-03-personal-wiki.md
  - collaboration/solo/STATE.md
  - collaboration/solo/LOG.md
forbidden_paths:
  - frontend/**
  - go-backend/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-030：统一助手的轻量时效信息能力

## 目标

普通对话默认保持零工具调用，但在 Root Resolver 判定为单一、明确的时效问题时，允许
一次受控的当前日期、天气或公开网页搜索；需要多来源比较、证据评估或显式选择时才进入
Research，并将其用户名称收敛为“联网调研”。

## 实现约束

- 不新增第二个 Root Graph、Agent 入口、模型 Gateway 或工具执行路径；
- 工具调用必须经过既有 Capability Registry 的白名单、Schema、预算、超时和审计；
- 普通对话每轮最多调用一个只读 Capability，稳定问答继续为零次；
- 天气使用确定性结构化数据源，不让搜索摘要代替天气数据；
- `tavily_search` 保留为历史兼容名，新执行路径使用供应商无关的 `web_search`；
- 模型原生推理由服务端 Profile 决定，不新增或恢复“深度思考”Skill/用户开关；
- Research 根据计划复杂度使用 0/1/N 次检索，不再默认把简单目标扩张到五次。

## 非目标

- 不修改前端页面或交互；
- 不实现自由循环的通用 Agent Tool Loop；
- 不接入私有数据源、MCP 或插件市场；
- 不 Push、部署或执行生产操作。

## 验收标准

- [ ] 普通稳定问答不调用 Capability；
- [ ] 当前日期、指定地点天气和单一最新事实可分别调用对应 Capability；
- [ ] 轻量工具失败时不会编造实时结果，Run 仍可给出明确降级回答；
- [ ] 多来源调研继续进入 `research_v1`，并按 0/1/N 预算执行；
- [ ] Skills 公开目录显示“联网调研”，不出现“深度思考”Skill；
- [ ] 旧 `tavily_search` 名称仍可解析历史配置和测试数据。

---
id: TASK-012
title: 建立统一助手前端与 Skill 交互
status: draft
executor: grok
base_commit: pending
business_round: ROUND-02
depends_on:
  - TASK-007
  - TASK-011
source_todos:
  - "docs/architecture/agent-runtime-migration-progress.md#产品架构主线TODO1：移除普通/深度思考Agent选择"
  - "docs/architecture/agent-runtime-migration-progress.md#P1：Skill快捷按钮与composer chip"
  - "docs/product/recruiting-mvp.md#5-7：Skill触发、可见性与对话页面"
  - "docs/design/qidian-web-visual-ux-spec.md#10：ROUND-02统一助手前端迁移"
  - "docs/decisions/ADR-013-qidian-frontend-migration-sequence.md"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - frontend/index.html
  - frontend/public/favicon.svg
  - frontend/public/brand/**
  - frontend/src/assets/**
  - frontend/src/brand/**
  - frontend/src/components/chat/**
  - frontend/src/features/skills/**
  - frontend/src/features/runs/**
  - frontend/src/lib/chat-api.ts
  - frontend/src/hooks/**
  - frontend/src/pages/AuthPage.tsx
  - frontend/src/pages/Index.tsx
  - frontend/src/index.css
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-012-*.md
forbidden_paths:
  - backend/**
  - go-backend/**
  - frontend/src/auth/**
  - go-backend/internal/platform/postgres/migrations/**
  - docker-compose.yml
---

# TASK-012：统一助手前端

## 目标

在 ROUND-01 已验收、统一 Skill 协议稳定后，一次将正式前端从奇点 AI 迁移为启点，
删除面向用户的永久“深度思考”Agent 模式，将聊天入口收敛为一个启点助手，并支持
真实的显式 Skill、自动选择结果、确认和结构化活动展示。

## 交付内容

- 按 `docs/design/qidian-web-visual-ux-spec.md` 迁移产品名、助手名、favicon、
  metadata、全局 Design Token、登录页、应用外壳、侧栏、对话空白页和消息视觉；
- 使用文档式、克制的启点视觉方向，不逐像素复刻概念稿，也不复制已归档奇点 AI
  代码；
- 清理 Lovable Open Graph/Twitter 遗留内容；
- 删除“深度思考”开关和 `deep -> research_agent` 映射；
- 新请求使用 `model_id=auto` 和可选 `requested_skill`；
- `/` 菜单只展示当前 available 且 UI visible 的 Skill；
- ROUND-02 必须支持 `/fortune`；`/decision` 在 TASK-021 将 Decision 标记
  available 后由同一动态菜单自动出现，TASK-012 不提前伪造入口；
- 显式选择以可移除 Skill Chip 展示；
- 回答顶部展示实际 Skill、自动/用户指定/兼容来源；
- 中置信度或 Fortune 自动选择显示确认交互；
- 确认操作创建一个正常后续 Turn，并以显式 `requested_skill` 执行；不假装恢复
  前一个已经完成的 Run；
- Activity、Citation、Artifact 与回答正文分层。
- 保留 ROUND-01 已验收的会话、Create/Attach/Cancel、恢复、失败和 Citation 语义；
- 图片附件仍未真实上传时隐藏入口，不继续发送 `[已附加图片]` 占位文本；
- 修复迁移涉及组件中的语义导航、表单名称、触摸目标、动态视口和焦点问题。

## 非目标

- 不增加模型选择器；
- 不建设 Skills 独立页面；
- 不实现 Wiki 或 Decision 业务；
- 不展示个人上下文数量、Wiki Proposal、Decision 卡或任何 ROUND-03～04 假数据；
- 不把 HTML 概念稿当作当前业务能力清单；
- 不保留“普通/深度思考”作为换名后的永久按钮；
- 不修改后端协议。

## 验收标准

- [ ] 前端不再提交 `agent_name`；
- [ ] 产品名、助手名、favicon、metadata 和页面外壳统一为启点；
- [ ] 不再出现奇点 AI、“奇”字、宇宙轨道、紫蓝品牌 Token 和 Lovable 元数据；
- [ ] 普通输入默认无显式 Skill；
- [ ] Slash 与 Chip 只对 available Skill 正确设置/清除 requested Skill；
- [ ] 自动路由结果可见；
- [ ] 确认前不会执行需确认 Skill；
- [ ] Activity 不进入回答正文；
- [ ] 移动端和桌面端基础交互可用；
- [ ] 深浅色、375/768/1024/1440px、键盘焦点和 44px 触摸目标通过检查；
- [ ] 页面不出现尚不可用的 Wiki、Context、Proposal 和 Decision 入口；
- [ ] 未实现真实图片上传前不显示附件入口；
- [ ] 现有会话、取消和恢复不回归。

## Grok必须验证

```text
cd frontend && npm run lint
cd frontend && npm run build
```

执行前复核测试脚本并补充 Slash、Chip、确认和路由结果的状态测试。

## Codex验收与E2E

本项在 Solo 模式下并入 ROUND-02 唯一一次产品 E2E。使用 Browser / Computer Use
验证启点登录和对话外壳、普通对话、显式 Fortune、自动 Research、Fortune 确认后的
新 Turn、移除 Chip、取消/刷新恢复、Citation 和旧会话显示；覆盖移动端、深浅色和
基础键盘操作。确认用户始终感知为同一个助手，并且 ROUND-02 不出现尚不可用的
Wiki、Proposal 或 Decision 入口。

## Handoff

写入 `collaboration/handoffs/TASK-012-round-1.md` 后停止。

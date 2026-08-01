---
id: TASK-015
title: 建立我的空间 API 与递归文档体验
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-014
source_todos:
  - "docs/product/recruiting-mvp.md#7.2：我的空间"
  - "docs/product/web-mvp.md#8：我的空间"
  - "docs/decisions/ADR-014：递归个人空间"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/wiki/**
  - go-backend/internal/documents/**
  - go-backend/internal/httpapi/wiki*.go
  - go-backend/internal/httpapi/document*.go
  - go-backend/internal/httpapi/space*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/httpapi/*wiki*_test.go
  - go-backend/internal/httpapi/*document*_test.go
  - go-backend/internal/httpapi/*space*_test.go
  - frontend/src/components/workspace/**
  - frontend/src/features/space/**
  - frontend/src/features/wiki/**
  - frontend/src/pages/**
  - frontend/src/lib/space-api.ts
  - frontend/src/lib/wiki-api.ts
  - frontend/src/App.tsx
  - frontend/src/App.css
  - frontend/src/index.css
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-015-*.md
forbidden_paths:
  - backend/**
  - go-backend/internal/platform/postgres/migrations/**
  - frontend/src/components/chat/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-015：我的空间 API 与递归文档体验

## 目标

让用户在统一启点工作区中从根目录逐层浏览、创建和管理文件夹，阅读和编辑 Markdown，
并从文档或上下文详情管理会长期影响回答的结构化信息。页面不再提供扁平“我的 Wiki”
数据后台。

## 路由与信息架构

```text
/space                              顶层文件夹
/space/folders/:folderId            当前目录直接子项
/space/documents/:documentId        文档阅读/编辑与当前目录上下文
/space/context/:itemId              结构化上下文详情（可用抽屉或路由化弹窗）
```

- 根页只展示顶层文件夹，不显示最近打开专区或全库文档表；
- Folder 页只展示直接子 Folder/Document，不一次展开整棵树；
- 排序为最近打开或名称 A–Z，文件夹始终在文件前，状态写入 URL；
- 面包屑每一级使用真实 Link，刷新、前进/后退和深链接恢复位置；
- 文档桌面页复用 256px 一级侧栏，并最多增加一个约 340px 当前目录上下文栏；
- 移动端上下文栏使用抽屉或分层页面，375px 起无横向页面溢出。

## API 能力

- 获取根目录和当前目录的直接子项、面包屑、分页与排序；
- 创建、重命名、移动和删除空文件夹；
- 创建、读取、编辑并生成 Document Revision、移动/重命名和永久删除文档；
- 文档 Markdown 返回安全原文，前端渲染危险 HTML/URL 必须清理；
- Wiki Item 创建、分页/搜索、详情、Revision/Source、修改、outdated、forgotten、恢复和
  永久删除；
- 结构化信息可按 Document/Revision 来源查询，不因删除原文静默删除已确认事实；
- 所有写入使用 CSRF、认证、用户隔离、幂等/乐观锁和明确冲突响应。

## 页面能力

- 一级导航增加“我的空间”，复用 `WorkspaceShell`、账户菜单、主题和 256px 侧栏；
- 根/文件夹使用可增长的网格或列表，长名称、空目录、加载、错误和大目录有完整状态；
- 文档阅读支持标题层级、代码、表格、列表、链接和长内容；
- 文档编辑有保存状态、并发冲突、离开未保存提醒和 Revision；
- 文件夹/文档移动、重命名和删除使用语义按钮、键盘焦点与明确确认；
- “关联上下文”入口展示确认事实/状态/规则/AI 分析、来源和 Revision，并提供原有
  暂时遗忘、恢复、永久删除能力；它不是另一个一级列表。

## 非目标

- 不实现文件夹上传编排（TASK-017）；
- 不实现 AI 提取或 Proposal（TASK-019/020）；
- 不实现向量检索、全局知识图谱或全量展开树；
- 不实现 Agent Document CRUD；
- 不实现 Office/PDF 预览或 Obsidian 同步。

## 验收标准

- [ ] 根、嵌套 Folder 与 Document 路由、面包屑、刷新和浏览器历史正确；
- [ ] 当前目录两种排序稳定，Folder 优先，分页/大列表不阻塞；
- [ ] Folder/Document 创建、编辑、移动、重命名、删除遵守 TASK-014 不变量；
- [ ] 文档编辑生成 Revision，冲突不会静默覆盖；
- [ ] Markdown 危险 HTML/URL 不执行；
- [ ] 结构化上下文可见、可修改、可遗忘/恢复/删除，AI analysis 不显示为 confirmed；
- [ ] 用户只能访问自己的 Folder、Document、Wiki 与 Revision；
- [ ] 375、768、1024、1440px 无页面横向溢出，键盘、焦点和语义导航可用；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

实现与 Handoff 必须记录三个 required Skill 如何影响信息架构、渐进披露、交互、响应式
和可访问性。

## Codex验收与E2E

使用 Browser / Computer Use 完成多层 Folder 浏览、深链接、两种排序、文档创建/编辑/
移动/删除、Revision/冲突、结构化上下文管理、刷新、移动端和跨用户拒绝。Round 全量
旅程只在全部 Task 完成后统一执行。

## Handoff

写入 `collaboration/handoffs/TASK-015-round-1.md` 后停止。

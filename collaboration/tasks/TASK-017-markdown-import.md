---
id: TASK-017
title: 建立 Markdown 单文件与递归文件夹导入
status: draft
executor: grok
base_commit: pending
business_round: ROUND-03
depends_on:
  - TASK-015
source_todos:
  - "docs/product/recruiting-mvp.md#8.2：Markdown Document"
  - "docs/product/web-mvp.md#9：Markdown与Obsidian"
  - "docs/decisions/ADR-014：文件夹导入"
required_skills:
  - frontend-design
  - ui-ux-pro-max
  - web-design-guidelines
risk: high
review_gate: required
codex_e2e: required
allowed_paths:
  - go-backend/internal/documents/**
  - go-backend/internal/httpapi/document*.go
  - go-backend/internal/httpapi/space*.go
  - go-backend/internal/httpapi/server.go
  - go-backend/internal/platform/postgres/document_*.go
  - go-backend/internal/platform/postgres/*document*_test.go
  - go-backend/internal/platform/postgres/migration_test.go
  - go-backend/internal/platform/postgres/migrations/*_document_import.sql
  - frontend/src/features/space/**
  - frontend/src/features/documents/**
  - frontend/src/lib/space-api.ts
  - frontend/src/lib/document-api.ts
  - frontend/src/pages/**
  - frontend/src/**/*.test.*
  - collaboration/handoffs/TASK-017-*.md
forbidden_paths:
  - backend/**
  - frontend/src/components/chat/**
  - docker-compose.yml
  - docker-compose.dev.yml
---

# TASK-017：Markdown 与递归文件夹导入

## 目标

支持用户导入单篇 UTF-8 Markdown，或选择一个包含嵌套目录和多篇 Markdown 的文件夹，
在“我的空间”中保留安全相对路径和层级。导入完成后给出可理解摘要；本 Task 不进行 AI
提取，也不建立 Obsidian 同步。

## 导入协议

浏览器先构造有界 manifest，至少包含：

```text
batch_id
target_folder_id
root_name
entries[].kind
entries[].relative_path
entries[].size
entries[].content_hash（可由服务端复核）
```

Markdown 内容使用受控 multipart/stream 上传；服务端不信任浏览器路径、hash、MIME 或
扩展名。进入 `ready` 前冻结单批文件数、总大小、单文件大小、目录深度、路径长度、
超时和幂等键。

第一版只把 `.md`/`text/markdown` 作为 Document。其他文件列入“未导入”摘要，不静默
丢失提示；由受支持文件路径推导所需 Folder。空目录和仅包含不支持文件的目录不作为
Round 验收承诺。

## 安全与冲突

- 路径统一规范化分隔符并拒绝绝对路径、盘符、UNC、`..`、NUL 和越界长度；
- 文件名永不直接拼接服务端路径，不保存本地绝对路径；
- 浏览器不会上传软链接；若协议出现 link/special entry，服务端必须拒绝；
- UTF-8、扩展名、MIME、大小和内容均校验，Markdown 渲染仍走安全清理；
- 同一路径且 hash 相同返回 `skipped_duplicate`；
- 同一路径但内容不同返回 `conflict`，默认不覆盖，用户可改目标/名称后重试；
- 同一幂等键重复提交返回同一批次结果；
- 预检通过后的数据库写入按批次事务执行，验证或存储失败不留下半棵目录；
- 非 Markdown 跳过不是事务失败，但必须逐项出现在结果摘要；
- 导入文档不自动成为 confirmed fact，也不自动触发全库提取。

## 页面交互

- “导入文件夹”为主要动作，“导入 Markdown”为次级动作；
- 选择后先展示根目录名、Markdown 数量、总大小、目标位置、冲突与跳过项；
- 用户明确确认后上传，展示可取消的进度与 `aria-live` 状态；
- 成功摘要区分新增、重复跳过、冲突、格式不支持和失败；
- 成功后进入导入的顶层 Folder，不把根页改成最近文件列表；
- 在根页导入单篇 Markdown 时先选择现有 Folder 或创建 Folder，不在根目录直接产生
  Document；
- 移动端不能依赖拖放作为唯一入口。

## 非目标

- 不做 Obsidian 单向/双向实时同步或本地文件监听；
- 不导入 Office、PDF、图片、音视频或附件正文；
- 不批量执行 AI 提取；
- 不实现 Agent Document CRUD；
- 不用覆盖导入实现文档版本合并。

## 验收标准

- [ ] 单篇和嵌套文件夹导入均保留预期 Folder/Document 层级；
- [ ] 刷新和重新登录后原文、Revision、来源与目录仍存在；
- [ ] 同 hash 重复导入幂等跳过，同路径不同内容不覆盖；
- [ ] 路径逃逸、超限、错误编码、伪造 MIME、危险内容和 link entry 被拒绝；
- [ ] 非 Markdown、冲突和失败均有逐项可理解摘要；
- [ ] 批次失败不留下半写入或孤儿 Folder；
- [ ] 用户隔离、CSRF 和能力关闭正确；
- [ ] 键盘、焦点、移动端与长文件名可用；
- [ ] 不修改禁止范围。

## Grok必须验证

```text
cd go-backend && go test ./...
cd frontend && npm run lint
cd frontend && npm run build
```

使用固定的嵌套目录 fixture 覆盖重复、冲突、路径逃逸、超限和事务失败。Task 进入
`ready` 时按当时 Migration 目录分配下一序号，并把通配文件名收窄为唯一 Migration。

## Codex验收与E2E

使用 Browser / Computer Use 导入真实嵌套 Markdown fixture，验证预检、层级、刷新、
重复、冲突、错误文件、失败原子性、移动端和跨用户拒绝。Round 全量旅程在全部 Task
完成后统一执行。

## Handoff

写入 `collaboration/handoffs/TASK-017-round-1.md` 后停止。

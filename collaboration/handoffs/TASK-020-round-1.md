# TASK-020 Handoff · Round 1

## 基线与工作树

- base commit：`5f176a5`
- branch：`codex/round-03-solo`
- executor：Codex（Solo Protocol）
- 产品级 E2E：按 Solo Protocol 延后到 ROUND-03 唯一一次全量 E2E

## 修改文件

- `go-backend/internal/httpapi/proposal.go`
- `go-backend/internal/httpapi/proposal_integration_test.go`
- `frontend/src/lib/proposal-api.ts`
- `frontend/src/lib/proposal-api.test.ts`
- `frontend/src/features/proposals/ProposalReviewCard.tsx`
- `frontend/src/features/proposals/ProposalReviewCard.test.tsx`
- `frontend/src/features/proposals/RunProposalList.tsx`
- `frontend/src/features/proposals/proposal-presentation.ts`
- `frontend/src/features/proposals/proposal-presentation.test.ts`
- `frontend/src/features/wiki/DocumentContextPanel.tsx`
- `frontend/src/components/chat/ChatMessage.tsx`

## 行为变化

- 新增可复用 Proposal 审阅卡，在文档关联上下文与带 Run 的对话结果中保持一致语义；
- 提供接受、修改后接受、暂缓、拒绝四种显式用户动作；
- 显示类型、领域、操作、来源片段、Document Revision、置信度、冲突、原建议与最终采用内容；
- 更新候选按需读取当前 Wiki 原内容，接受后刷新关联上下文但不修改 Markdown；
- 失败提供可恢复提示，旧版本冲突不会静默覆盖，同请求重试复用幂等键；
- 处理状态由 Go 事实源返回，刷新后仍可恢复；历史处理记录留在原文档上下文，不新增独立收件箱；
- Proposal API 支持按 `run_id` 筛选带有 Run provenance 的候选，并保持用户隔离。

## 三个前端 Skill 的影响

- `frontend-design`：沿用启点绿、文档式排版与低噪声卡片，只把用户决定和证据做成清晰视觉层级；
- `ui-ux-pro-max`：使用渐进披露查看原文/依据，四个动作保持显式，修改和拒绝使用焦点受控对话框；
- `web-design-guidelines`：全部操作使用语义按钮与可见焦点，异步/错误状态使用 live region，保留 44px 触控目标、长内容换行、危险操作确认和失败恢复。

## 验证结果

- `cd go-backend && go test ./...`：passed；
- 隔离 PostgreSQL `TestWikiProposalHTTPIntegration`：passed，覆盖未授权/CSRF、原样接受、修改接受、暂缓、拒绝、重复提交、Run 筛选、详情原内容、Revision 冲突和跨用户隔离；临时数据库与角色已删除；
- `cd frontend && npm test -- --run`：16 files / 61 tests passed；
- `cd frontend && npm run lint`：0 errors，保留 8 条既有 Fast Refresh warnings；
- `cd frontend && npm run build`：passed，保留既有 browserslist 与 bundle size warnings；
- `git diff --check`：passed。

## 偏差、未完成与风险

- 当前 ROUND-03 只有文档提取路径实际创建 Proposal；对话组件已经支持展示带 `run_id`/`origin_run_id` provenance 的 Proposal，但没有新增另一条 Proposal 创建链路；
- 文档来源链接携带 Revision 查询参数并展示 Revision ID，本 Task 不扩展 Document Router 的历史 Revision 切换语义；
- 浏览器中的键盘、移动端、刷新、重复点击和真实失败恢复统一进入 Round E2E；
- 未修改 Markdown、Migration、Python Runtime、生产配置或外部 API。

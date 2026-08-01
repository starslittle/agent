# TASK-019 Handoff · Round 1

- baseline：`f3ac11f`（TASK-018 completion state）；
- worktree：`C:/Users/10245/Desktop/qidianAgent-round-03-solo`；
- branch：`codex/round-03-solo`；
- result：completed；

## 行为变化

- 文档详情新增“从当前版本提取”入口，只冻结并分析用户明确打开的一篇 Markdown Revision，不遍历 Folder；
- 提取复用既有 Product Run、Route Resolve、Context Package、Runtime 事件与 Model Gateway，稳定使用 `run_purpose=document_extraction`；
- Markdown 作为不可信 user content 进入无工具、无网络的结构化模型请求，强类型输出最多 30 条候选，并保留 candidate type/domain/content、位置/片段、confidence、create/update、公开解释和提取/Prompt/模型版本；
- Go 仅在受控隐藏提取 Run 的 `document.extraction.completed` 事件上投影 Proposal；失败 Run 不创建 Proposal、不写 Wiki、不改 Document；
- Proposal ID 由用户、Document、Revision、提取版本和候选内容稳定派生；显式重试不会复制相同候选，新 Revision 会产生独立候选且旧 Proposal 继续引用旧 Revision；
- 提取内部 Conversation 不出现在聊天历史，Product Run 仍可从状态卡及 Agent Runs 查看真实时间线；
- 文档侧栏显示运行中、失败/重试、Run 链接、候选总数、冲突/低置信度摘要与只读待确认列表，确认动作仍留给 TASK-020。

## 修改文件

- `backend/agent/documents/**`
- `backend/agent/prompts/document_extract_v1.txt`
- `backend/app/runtime/langgraph_v1.py`
- `backend/tests/unit/test_document_extraction.py`
- `go-backend/internal/agent/types.go`
- `go-backend/internal/agent/types_test.go`
- `go-backend/internal/conversation/document_extraction.go`
- `go-backend/internal/conversation/service.go`
- `go-backend/internal/httpapi/document_extraction.go`
- `go-backend/internal/httpapi/document_extraction_integration_test.go`
- `go-backend/internal/httpapi/server.go`
- `frontend/src/lib/document-api.ts`
- `frontend/src/features/wiki/DocumentContextPanel.tsx`

## 验证

- `cd backend && uv run pytest tests -q`：108 passed，2 skipped；
- `cd go-backend && go test ./...`：passed；
- 隔离 PostgreSQL 15 + 真实 HTTP/Supervisor/伪固定 Runtime integration：passed，覆盖 Prompt injection fixture、失败不写、重试去重、新旧 Revision 可追溯、隐藏 Conversation；
- `cd frontend && npm run lint`：0 errors，保留 8 条既有 Fast Refresh warning；
- `cd frontend && npm run build`：passed，保留既有 bundle 体积与 browserslist warning；
- `git diff --check`：passed；
- 按 Solo Protocol 未执行逐 Task Browser E2E，统一进入 ROUND-03 唯一产品 E2E。

## 三个前端 Skill 的影响

- `frontend-design`：延续启点文档式侧栏和绿/珊瑚品牌，不引入独立任务中心或通用蓝色 AI 面板；
- `ui-ux-pro-max`：将“提取”设计为当前 Revision 的渐进式次级操作，明确运行、失败、摘要和只读候选层级；
- `web-design-guidelines`：使用语义 Button/Link、`aria-live`/`role=alert`、可见焦点、非颜色状态表达和移动端既有 Sheet 复用。

## 偏差、风险与清理

- 为复用现有 Product Run 而不新增 Run Schema，Document/Revision 关联冻结在内容寻址的受控请求与持久事件中；没有建立第二套队列或任务表；
- 第一版单次提取上限为 16,000 Unicode 字符，超过时明确失败，不静默截断；Document 本身仍保留更大的存储上限；
- 冲突候选使用同 type/domain 的已确认或过时 Wiki 条目作为可能目标，最终确认与编辑由 TASK-020 决定；
- 固定 Provider fixture 不依赖真实模型；真实 Provider 质量、嵌套目录 Browser 操作和响应式视觉留到 Round E2E；
- 集成验证创建的临时 PostgreSQL database/role 已在每次测试后删除；未 push、merge、部署或修改生产环境。

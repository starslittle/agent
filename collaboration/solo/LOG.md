# Solo Execution Log

只记录 Solo 模式下的最小交付摘要，不复制完整测试输出、Handoff 或 Review。

## Existing Baseline

### TASK-002

- commit：已合入 `main`，历史提交与证据见原 Handoff/Review；
- result：completed；
- summary：Browser Event、Activity 与回答正文完成结构化分离；
- validation：由原 Codex/Grok 流程完成；
- risk：保留原 Review 中记录的非目标。

### TASK-003

- commit：已合入 `main`，详细提交见 `collaboration/reviews/TASK-003-round-2.md`；
- result：completed；
- summary：Create Run 与 Go Run Supervisor 已完成并验收；
- validation：Go 测试、PostgreSQL integration、Create API E2E 和旧聊天回归通过；
- risk：保留原 Review 中记录的后续门禁。

### TASK-004

- commit：`f73245f`；
- result：completed；
- summary：新增持久化 Run Event Attach/Re-attach SSE，支持游标重放、活动追随、唯一终态、序列缺口 fail-closed、断连不取消和用户隔离；
- validation：`cd go-backend && go test ./...`；
- risk：Attach 当前采用 PostgreSQL 短轮询；生产参数优化不在本 Task 范围。

### TASK-005

- commit：`edfee36`；
- result：completed；
- summary：前端切换到 Create→Attach/Re-attach→Cancel，支持 sequence 续接、刷新恢复、停止失败重试和服务端终态；
- validation：`npm run lint`、`npm run test -- --run`（19 tests）、`npm run build`；
- skills：保留既有聊天视觉语言，强化 44px 触控目标、焦点、IME、状态播报和 reduced-motion；
- risk：lint 保留 8 条仓库既有 Fast Refresh warning；产品级场景统一在 Round E2E 验证。

### TASK-006

- commit：`b4c7ecb`；
- result：completed；
- summary：新增统一 P0 Runtime 验收入口、9 项 Product Run 风险映射，以及不持久化命令输出或敏感内容的 JSON/Markdown 摘要；
- validation：隔离 PostgreSQL `full` profile，11 suites passed、9 risks passed；
- risk：完整模式要求调用方提供专用测试数据库；报告目录被 Git 忽略，需由每次执行重新生成。

### TASK-007

- commit：`069ef2b`；
- result：completed；
- summary：Research Citation 以结构化事件进入 Run/Event/Message，Go 白名单校验并持久化，前端提供精确角标、来源列表、刷新恢复和带来源复制；
- validation：Python 62 passed/2 skipped；Go 全包与隔离 PostgreSQL integration passed；前端 lint 0 errors、25 tests、build passed；
- skills：沿用现有聊天视觉，以稳定编号、原生链接、44px 命中区、可见焦点和长内容换行满足信息层级与可访问性；
- risk：lint 保留 8 条既有 Fast Refresh warning，构建保留既有 bundle 体积提示；产品场景进入 Round E2E。

## ROUND-01 Acceptance

- accepted commit：`1171358`；
- result：accepted；
- summary：真实浏览器完成普通与 Research 对话、Activity/正文/Citation 分层、刷新与页面断开恢复、取消/重试/竞态、失败/超时后续发、刷新引用与复制、历史和跨用户隔离；验收中修复恢复订阅生命周期和仅对 `run_create_not_enabled` 启用的 legacy fallback；
- rollback：同一数据库保留 schema 与历史，`v1 → legacy` 后普通对话、历史、隔离通过，再切回 `v1` 后新 Run 以 protocol v1 完成；未执行 Down Migration；
- validation：Browser 产品 E2E 通过；隔离 PostgreSQL `full` profile 11 suites passed、9 risks passed（Python 62 unit、2 PostgreSQL integration、Go 全包与 PostgreSQL integration、前端 27 tests/lint/build、Compose 与 diff check）；
- risk：保留 8 条既有 Fast Refresh warning、既有 bundle 体积提示与 browserslist 数据陈旧提示；Fortune 当前仅有 Runtime 工作流入口，统一前端 `/fortune` 属于 ROUND-02 TASK-012；无本轮阻塞风险；
- cleanup：隔离 Go/Vite/测试 Agent、两套临时 PostgreSQL、测试账号/对话和临时报告已删除；未 push、merge 或部署。

## ROUND-02

### TASK-001

- commit：`5a1a619`；
- result：completed；
- summary：新增强类型 Skill Manifest、仅含 Research/Fortune 的配置与启动即失败的稳定 Registry，未接入现有请求链；
- validation：Skill tests 12 passed、Python unit 74 passed、Ruff passed；
- risk：无。

### TASK-008

- commit：`b32b286`；
- result：completed；
- summary：新增稳定 `model_id=auto` Catalog，封存受控 provider/profile/model/能力与限制快照，不接受请求侧 Provider 参数或 Secret；
- validation：Model tests 15 passed、Python unit 82 passed、Ruff passed；
- risk：Windows 不展开 pytest 文件 glob，已改用两个明确测试文件执行同一范围。

### TASK-009

- commit：`dd9acff`；
- result：completed；
- summary：建立 Go/Python/Browser 一致的 model/Skill Run 契约、兼容适配、稳定解析事件、不可变创建字段和 PostgreSQL CAS 投影，并以 expand-only Migration 保留旧数据；
- validation：Python 88 passed/2 skipped、Ruff passed；Go 全包 passed；隔离 PostgreSQL Migration、幂等及冲突写入 integration passed；前端 lint 0 errors（8 条既有 warning）与 build passed；
- risk：保留既有前端 bundle 体积与 browserslist 陈旧提示；临时 PostgreSQL 已删除，未连接现有开发库。

### TASK-010

- commit：`643be64`（跨服务冻结补充 `eb1c7f9`）；
- result：completed；
- summary：新增唯一 Root Skill Resolver，支持显式、结构化自动路由、稳定置信度边界、失败回退和 Fortune 强制确认，并在执行前冻结到 provenance/Run Event；
- validation：Root tests 21 passed、Python unit 98 passed、Ruff passed；Go 全包 passed；前端 lint 0 errors（8 条既有 warning）与 build passed；
- risk：路由模型使用默认模型目录和 Provider 超时策略；产品级真实模型效果与确认交互进入 Round E2E。

### TASK-011

- commit：`eef7e18`；
- result：completed；
- summary：Research/Fortune 通过 Skill Registry 进入原 Subworkflow，Manifest 成为 Capability、预算和 Skill 快照来源，Direct 与旧 Agent Alias 保持兼容；
- validation：Skill/Root targeted 27 passed；Python 全量 103 passed/2 skipped；Ruff passed；
- risk：Research/Fortune 工作流文件未改动；真实 Provider、Citation、取消与确认链进入 Round E2E。

### TASK-012

- commit：`83ac2cf`；
- result：completed；
- summary：正式前端统一迁移为启点，新增未登录静态工作区预览、真实登录/注册页、Slash Skill 菜单与可移除 Chip；新 Run 仅发送 `model_id=auto` 和可选 `requested_skill`，确认操作创建显式后续 Turn，并展示权威 Skill 来源、Activity、Artifact、Citation 与正文分层；
- validation：前端 34 tests passed、lint 0 errors（8 条既有 warning）、production build passed；Browser 覆盖亮暗色、375/768/1024/1440、登录表单错误聚焦和未登录私有请求边界；
- skills：`frontend-design` 与 `ui-ux-pro-max` 收敛为文档式松石绿/珊瑚启点线视觉，`web-design-guidelines` 推动语义导航、单一 H1、动态视口、44px 触控、可见焦点、表单名称/错误关联与 reduced-motion；
- risk：完整登录后普通/Research/Fortune/确认/取消/恢复/Citation 场景按 Solo 协议并入 Round 唯一一次产品 E2E；保留既有 bundle 体积与 browserslist 陈旧提示。

### TASK-013

- commit：`471f3f3`；
- result：completed；
- summary：新增普通用户 Agent Runs 列表和详情，支持状态筛选、游标分页、移动端列表/详情路由、运行状态、稳定 sequence 时间线、Skill/Workflow/Model、Capability/Tool、Artifact/Citation、Token/调用/耗时、错误与 provenance 摘要，并从当前聊天回答链接到关联 Run；
- validation：前端 41 tests passed、lint 0 errors（8 条既有 warning）、production build passed；未登录 `/agent-runs` Browser 门禁跳转登录且未请求 Agent Runs API；
- skills：延续 TASK-012 的启点视觉和响应式外壳，以用户问题“这次任务发生了什么”组织信息；状态控件、分页、深链接、44px 触控和错误/空/加载状态遵循 Web Guidelines；
- risk：前端明确忽略 Prompt 集合、Span attributes 和 Event 原始 data，仅对白名单 Citation/Artifact 字段投影；真实完成/取消/失败 Run 的页面验收进入 Round E2E。

### TASK-028

- commit：`aa52418`；
- result：completed；
- summary：新增独立 `/api/v1/internal/agent-runs` 只读权限边界、`observability_admin` 角色、跨用户筛选/详情、fail-closed 访问审计与服务端脱敏投影；前端复用 Agent Runs 状态、时间线、Usage、Capability、Citation、Artifact 和 provenance 组件，普通用户无入口且稳定拒绝；
- validation：Go 全包 passed；隔离 PostgreSQL Migration、跨用户筛选/详情及审计 integration passed；前端 46 tests passed、lint 0 errors（8 条既有 warning）、production build passed；Browser 覆盖普通用户拒绝、管理员组合/时间筛选、空状态、完成/取消/失败详情、审计、375/1440 响应式、无写操作和敏感字段不出现；
- skills：`frontend-design` 与 `ui-ux-pro-max` 延续启点文档式信息层级，`web-design-guidelines` 推动显式标签、44px 控件、空/错/加载状态、移动端详情隐藏筛选区和管理员移动端入口；
- risk：权限仅支持 `user`/`observability_admin` 两级且无产品内提权入口；生产授权与账号授予不在本轮范围；保留既有 bundle、browserslist 与 React Router warning。

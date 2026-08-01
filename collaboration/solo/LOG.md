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

### ROUND-02 Acceptance Blocker

- result：blocked；
- summary：Round 文档要求的 `unified_agent_enabled` 与 `agent_observability_enabled` 尚无代码实现，既有 Task 也未授权实现所需的跨服务路径，无法执行独立关闭、回滚与重新启用演练；
- validation：仓库全文检索确认两个逻辑能力名仅存在于 `collaboration/rounds/README.md` 与 `ROUND-02-unified-agent.md`；TASK-028 产品场景及代码验证已通过；
- risk：在新增纠偏 Task 并冻结统一 Agent 关闭后的 ROUND-01 回退语义前，ROUND-02 不能标记为 accepted。

### ROUND-02 Acceptance Decision

- result：resolved；
- summary：用户决定本轮暂不实现两个能力开关，统一助手保持唯一用户入口，内部观测继续由服务端管理员角色隔离；Round 验收改为统一路由、兼容读取与权限边界验证；
- validation：`ROUND-02-unified-agent.md` 与轮次 README 已同步，不再要求两个开关的关闭/重新启用演练；
- risk：生产级灰度与紧急停止机制留到发布准备阶段单独设计，本轮不提供应用级能力熔断。

### ROUND-02 E2E Confirmation Blocker

- result：blocked；
- summary：自动 Fortune 正确产生 `confirmation.required` 且未执行 Fortune，但新会话导航/刷新会重新水合消息并丢失确认卡，用户无法创建显式后续 Turn；
- validation：真实 Browser 复现两次，Agent Run 时间线均包含 `confirmation.required`；前端局部状态合并测试 2 passed，但无法覆盖新会话重挂载；
- risk：持久修复需要最小修改 TASK-012 禁止的 Go 消息事件投影与测试路径，等待用户授权。

### TASK-012 E2E Fix

- commit：`8bda499`；
- result：completed；
- summary：将脱敏 `confirmation.required` 投影到助手消息 metadata，前端刷新/重挂载后用前一条用户消息恢复确认动作，点击后仍创建独立显式 Skill Turn；
- validation：Go conversation targeted passed；隔离 PostgreSQL `TestConversationLifecycleIntegration` passed；前端状态恢复 3 tests passed、lint 0 errors（8 条既有 warning）、production build passed；Browser 刷新确认卡、显式后续 Turn 与 `fortune_v1` provenance passed；
- skills：保持既有启点视觉，仅补状态恢复；确认按钮继续使用语义 button、清晰文案和既有 44px 触控边界；
- risk：确认 metadata 只保存 Skill、置信度和固定 reason code，不复制用户 prompt 或任意事件字段。

### TASK-009 E2E Fix

- commit：`a95c0b2`；
- result：completed；
- summary：当 Supervisor 已将 Run 置为终态但 Python 未产生终态事件时，Browser SSE 合成一次不落库的 `done`，避免前端无限重连和持续显示停止按钮；
- validation：Go `TestAttachRunEvents*` targeted passed；Browser 验证失败及时显示“生成未完成”，服务恢复后同一对话可继续；旧 `fortune_agent` 映射为 `fortune / compatibility / fortune_v1`，未知 Skill 返回 400；
- risk：合成终态仅存在于浏览器投影层，序号紧随持久事件 cursor，不修改 Runtime 事件历史。

### ROUND-02 Acceptance

- accepted commit：`a95c0b2`；
- result：accepted；
- summary：统一启点入口、Direct/显式与自动 Research、显式与需确认 Fortune、Skill Chip、用户 Run、管理员只读观测、兼容读取与安全回退均通过；本次恢复只复验此前未通过或受修复影响的确认、失败、取消和兼容链路，没有重复已通过场景；
- validation：沿用本轮已通过的 Python 103 unit、Go 全包、前端 46 tests/lint/build、隔离 PostgreSQL Go/Python integration 与既有 Browser 主旅程；新增确认投影/刷新/显式 Turn、取消刷新后继续、无终态事件失败恢复、旧 `agent_name` 与未知 Skill 验收均通过；
- risk：按产品决定不提供 `unified_agent_enabled` 和 `agent_observability_enabled`；生产灰度与紧急停止留待发布准备，保留既有 8 条 Fast Refresh warning、bundle 体积和 browserslist 陈旧提示；
- cleanup：本轮隔离 PostgreSQL/Redis/Python/Go/Vite 容器、测试账号与对话、临时网络/卷/镜像已删除；未 push、merge、部署或修改生产环境。

## ROUND-03 Start

- authorization：2026-08-01 用户明确授权启动 ROUND-03；
- base：`c285fef00de10eccd042cb94313727fa5ba2c3bb`；
- execution：`codex/round-03-solo` 单一 Round worktree，连续执行 TASK-014～020、TASK-029；
- boundary：不包含 push、部署、生产操作、破坏性数据操作或 ROUND-04 授权。

### TASK-014 · accepted

- commit：`5c9b0f6`；
- result：建立递归 Space Folder、Markdown Document/Revision 与 Wiki Item/Revision/Source/Tombstone 的 Go/PostgreSQL 事实源，强制 user ID、稳定 ID、乐观锁、路径和删除不变量；
- validation：`go test ./...` 通过；隔离 PostgreSQL 15 中验证干净/重复 Migration、目录环/冲突、跨用户隔离、Revision、遗忘/恢复/永久删除，以及文档删除与已确认 Wiki 生命周期独立；
- risk：本 Task 尚无 HTTP/UI 入口；永久删除二次确认由后续 API/UI Task 强制。

### TASK-015 · accepted

- commit：`08fafdb`；
- result：交付 `/space` 递归文件桌面、Folder/Document/Context 深链接、排序分页、Markdown 阅读编辑与 Revision、移动/重命名/确认删除，以及认证/CSRF/幂等/乐观锁 API；
- skills：`frontend-design` 保留启点绿/珊瑚与文档式阅读视觉，拒绝通用蓝色模板；`ui-ux-pro-max` 促成逐层披露、48 项分页、移动端 Sheet、44px 操作区和完整空/错/加载状态；`web-design-guidelines` 约束语义 Link/Button、焦点、面包屑 URL 状态、危险操作确认、Intl 日期和 Markdown URL/HTML 清理；
- validation：隔离 PostgreSQL 15 下 `go test ./...` 通过；前端 54 tests、`tsc --noEmit`、lint（仅保留既有 8 条 Fast Refresh warning）和 build 通过；
- deviation：Task 契约漏列真实服务接线所需的 `go-backend/cmd/server/main.go`，已提前说明并仅扩展这一文件，未修改其他禁止范围；
- risk：产品级 Browser E2E 按 Solo Protocol 延后到 Round 完成后统一执行，bundle 体积与 browserslist 为既有警告。

### TASK-016 · completed

- commit：`8eb2f4b`；
- result：在同一 Product Run 内建立 Resolve → Context → Execute，两阶段复用唯一 Root Skill Resolver；Go 只从当前用户已确认且有效的 Wiki 条目按类型、领域、数量和字符预算冻结 Context Package，Python 复用冻结解析且不回查 Wiki，Run、对话与上下文详情展示实际 Item/Revision 来源；
- validation：Python 全量 104 passed/2 skipped；Go 全包 passed；隔离 PostgreSQL 15 的 Migration、状态过滤、跨用户隔离、历史 Revision 冻结和永久删除脱敏 integration passed；前端 `tsc --noEmit`、lint（仅既有 8 条 Fast Refresh warning）与 build passed；
- skills：`frontend-design` 保持启点文档式层级，`ui-ux-pro-max` 将上下文依据作为次级可追溯信息，`web-design-guidelines` 约束语义链接、焦点、长 ID 与空状态；
- risk：Context 第一版采用确定性类型/领域/时间排序，不引入向量检索；路由调用 15 秒超时并失败关闭，产品级真实 Provider 与 Browser 场景进入 Round 唯一 E2E。

### TASK-017 · completed

- commit：`da4700e`；
- result：交付 Markdown 单文件与递归文件夹导入，保留安全相对层级，提供服务端冲突/重复预检、受控 multipart、幂等事务、逐项摘要、根目录目标选择与可取消上传；
- validation：Go 全包 passed；隔离 PostgreSQL 15 的 Migration、嵌套层级、根目录导入、重复/冲突、幂等、失败回滚、跨用户和 Personal Space HTTP integration passed；前端 lint（仅既有 8 条 Fast Refresh warning）与 build passed；
- skills：`frontend-design` 保持启点文件桌面与品牌视觉，`ui-ux-pro-max` 将流程拆成选择、预检、确认和结果，`web-design-guidelines` 约束键盘入口、44px 控件、焦点、aria-live/progressbar、长路径与移动端非拖放入口；
- risk：文件夹浏览器 API 不承诺空目录和仅含不支持文件的目录；真实浏览器递归选择、取消上传与移动端场景进入 Round 唯一 E2E，保留既有 bundle 与 browserslist 警告。

### TASK-018 · completed

- commit：`e929602`；
- result：建立 Go/PostgreSQL 拥有的 Wiki Update Proposal、pending/deferred 可处理状态机、接受/修改接受/暂缓/拒绝 API、同目标 superseded、双来源 Wiki Revision 事务与动作幂等审计；
- validation：Go 全包 passed；隔离 PostgreSQL 15 的干净 Migration、原样/修改接受、Revision 冲突、失败回滚、重复和同键/异键并发、暂缓/拒绝、superseded、Fortune narrative 阻断、跨用户与 HTTP auth/CSRF integration passed；
- risk：本 Task 不暴露 Proposal 创建 HTTP，Agent/提取只能经 Go 内部服务产生待确认项；Browser 确认 UI 与产品 E2E 留到 TASK-020 和 Round 唯一验收。

### TASK-019 · completed

- commit：`bfc8302`；
- result：对用户明确打开的一篇 Markdown Revision 启动受控 `document_extraction` Product Run，以无工具/无网络的强类型 Model Gateway 提取候选，并仅通过完成事件幂等投影 Proposal；失败不写 Wiki/Document，隐藏内部 Conversation 不污染聊天历史；
- validation：Python 全量 108 passed/2 skipped；Go 全包 passed；隔离 PostgreSQL 15 的真实 HTTP → Route → Supervisor → Event → Proposal integration passed，覆盖 Prompt injection fixture、失败不写、重试去重、新旧 Revision 追溯与隐藏 Conversation；前端 lint 0 errors（保留既有 8 warnings）和 build passed；
- skills：`frontend-design` 保持启点文档式视觉，`ui-ux-pro-max` 将提取作为当前 Revision 的渐进次级操作，`web-design-guidelines` 约束语义控件、焦点、运行/失败 live 状态及只读候选展示；
- risk：单次提取明确限制为 16,000 字符；冲突第一版按同 type/domain 已确认或过时条目提示，最终确认和编辑由 TASK-020 完成；真实 Provider 与 Browser 产品旅程进入 Round 唯一 E2E。

### TASK-020 · completed

- commit：`b15d8b3`；
- result：在文档关联上下文与带 Run 的对话结果中复用同一 Proposal 审阅卡，提供接受、修改后接受、暂缓和拒绝，显示原建议/最终内容、当前 Wiki 原内容、来源片段、Document Revision、置信度与冲突，并保持刷新恢复、幂等和旧版本冲突保护；
- validation：Go 全包 passed；隔离 PostgreSQL 15 的真实 HTTP integration passed，覆盖原样/修改接受、暂缓、拒绝、重复提交、Run 筛选、详情原内容、Revision 冲突、认证/CSRF 和跨用户隔离；前端 61 tests passed、lint 0 errors（保留既有 8 warnings）与 production build passed；
- skills：`frontend-design` 保持启点文档式低噪声视觉；`ui-ux-pro-max` 采用渐进披露与四个显式决定；`web-design-guidelines` 约束语义按钮、焦点、44px 触控、live 状态、危险操作确认和失败恢复；
- risk：当前产品只有文档提取实际创建 Proposal；对话结果已支持带 Run provenance 的候选但未新增另一条创建链路，真实键盘/移动端与刷新场景进入 Round 唯一 E2E。

### TASK-029 · completed

- commit：`3a77515`；
- result：新增 Skills 一级入口、搜索目录、路由化只读详情和“在对话中使用”；Python Manifest 生成公开字段白名单，Go 结合签名上游、Runtime readiness、产品策略和认证边界输出 effective Catalog，前端 Slash 菜单、建议卡、Skill Chip、Runs 与目录共用同一服务端事实源；
- validation：Python 111 passed/2 skipped；Go 全包 passed；前端 62 tests、`tsc --noEmit`、lint 0 errors（保留既有 8 warnings）与 production build passed；契约测试覆盖隐藏 Prompt/Secret、unknown 字段、hidden/unavailable、未映射 Capability、签名、产品白名单和安全错误；
- skills：`frontend-design` 延续启点品牌而拒绝通用 AI 紫色模板；`ui-ux-pro-max` 采用目录发现、路由化详情理解、统一对话执行；`web-design-guidelines` 约束 URL 搜索、语义控件、焦点恢复、44px 触控、live/error 状态和移动端 overscroll；
- risk：真实浏览器深链接/刷新/后退/键盘/响应式、网络失败和 Run 服务端复校验进入 Round 唯一 E2E；新增 Skill 需要 Python 公开文案与 Go 产品白名单双重评审。

### ROUND-03 E2E Fix

- commit：`b3fdcbd`；
- result：completed；
- summary：保留文档提取冻结 Context Package，已处理 Proposal 的确定性重放不再令 Run 失败；同一文档 Revision 的重复提取复用幂等 Run，失败重试使用显式新键；冷启动 `?skill=` 等待服务端目录后再预选 Skill；
- validation：Python 文档提取 4 passed；Go 全包 passed，真实 PostgreSQL 文档提取 integration passed；前端 63 tests、`tsc --noEmit`、lint 0 errors（8 条既有 warning）passed；Browser 复验重放、幂等提取和冷启动 Skill 深链接 passed；
- skills：保持启点既有视觉与信息架构，只修复状态恢复；服务端目录仍是唯一可见性事实源，键盘焦点、深链接和 44px 控件语义保持不变；
- risk：无新增产品语义；未执行 build，遵循用户对小改动不重复 build 的要求。

### ROUND-03 Acceptance Blocker

- result：blocked；
- summary：主验收旅程、跨用户隔离、ROUND-02 Direct/Research/Fortune、会话搜索、Agent Runs、普通用户内部观测拒绝、空/过期 Context、Fortune 不自动写事实和 Skills 服务端一致性均通过；
- validation：375、768、1024、1440px 下对话、空间、文档、Skills、Runs 共 20 个页面检查均无横向溢出，移动端导航抽屉和深链接可用；仓库检索确认 `personal_space_enabled`、`document_import_enabled`、`wiki_context_injection_enabled`、`wiki_proposal_write_enabled`、`skill_catalog_enabled` 没有 Runtime 实现；
- risk：Round 文档要求分别执行能力关闭、数据保留与重新启用演练，但现有 Task 未定义这些跨服务服务端控制及授权路径；在用户决定新增纠偏 Task 或调整 Round 验收边界前，ROUND-03 不能标记为 accepted。

### TASK-015 E2E Fix · 文档阅读体验

- commit：`5e739ba`；
- result：completed；
- summary：恢复当前文件夹直接子项栏与明确父目录返回入口，移动端改用目录抽屉；关联上下文改为按需右侧抽屉；新增独立 Markdown 阅读样式并使用首个 H1 作为阅读标题，避免标题重复；
- validation：Markdown 5 tests、`tsc --noEmit`、lint 0 errors（8 条既有 warning）及 production build passed；Browser 验证 1440px 当前目录栏和唯一返回入口、375px 目录抽屉、标题/列表语义与样式、无横向溢出 passed；
- skills：`frontend-design` 保持启点文档式阅读与低噪声品牌层级；`ui-ux-pro-max` 分离常驻目录和按需上下文，保留可预测返回；`web-design-guidelines` 约束真实 Link、44px 控件、焦点、标题层级、长内容与移动端 overscroll；
- risk：ROUND-03 服务端能力控制验收阻塞仍然存在，本修复不改变该结论。

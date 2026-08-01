# TASK-029 Handoff · Round 1

## 基线与工作树

- base commit：`de3c8db`
- branch：`codex/round-03-solo`
- executor：Codex（Solo Protocol）
- 产品级 E2E：按 Solo Protocol 延后到 ROUND-03 唯一一次全量 E2E

## 修改范围

- Python Manifest 与安全公开投影：`backend/agent/skills/**`、`backend/configs/skills.yaml`、`backend/app/api/agent_runs.py`；
- Go 内部客户端、产品白名单与用户 API：`go-backend/internal/agentclient/**`、`go-backend/internal/skills/**`、`go-backend/internal/httpapi/skill*.go`、`server.go`；
- 前端共享 Catalog、目录/详情、导航、对话和 Runs：`frontend/src/features/skills/**`、`frontend/src/lib/skill-api.ts`、`frontend/src/pages/SkillsPage.tsx`、`frontend/src/App.tsx` 及相关共享组件。

## 行为变化

- Python Registry 从 Manifest 生成字段白名单固定的公开 Skill 投影；Capability 和 Context 只输出显式审核过的公开文案；
- Runtime 模型/Capability readiness 决定 `effective`，内部不可用原因不输出；
- Go 使用签名内部请求读取 Catalog，严格拒绝未知 JSON 字段，并按产品策略只向认证用户输出 effective 的 `research`、`fortune`；
- 新增 `/api/v1/skills` 与 `/api/v1/skills/:skillId`，未知或不可用深链接只返回安全状态；
- 新增 Skills 一级导航、可搜索目录、`/skills/:skillId` 路由化详情；桌面端为 Dialog，移动端为全屏详情；
- “在对话中使用”进入 `/?skill=:skillId` 并预选 Skill，发送 Run 时仍由服务端重新校验；
- Slash 菜单、首页建议、消息 Skill Chip、Agent Runs 与 Skills 页面共用同一 Catalog Provider，不再维护前端可用性静态列表；
- 内置 Skill 仍为只读，不提供编辑、开关、卸载、复制、测试或发布。

## 安全与三个前端 Skill

- Python/Go 双层白名单不返回 Workflow、Prompt、Schema、预算、Secret、内部 Capability ID、工具参数或内部禁用原因；未知字段和未映射 Capability 失败关闭；
- `frontend-design`：延续启点绿、圆点轨迹和文档式卡片，不采用通用 AI 紫色 Marketplace 模板；
- `ui-ux-pro-max`：目录负责发现，路由化详情负责理解，CTA 负责回到统一对话；移动端全屏、桌面 Dialog，状态与深链接保持一致；
- `web-design-guidelines`：搜索状态进入 URL；使用语义 Link/Button/Label、可见焦点、44px 触控、`aria-live`、Dialog 标题描述、Escape、关闭焦点恢复和 overscroll containment。

## 验证结果

- `cd backend && uv run pytest tests -q`：111 passed，2 skipped；
- `cd go-backend && go test ./...`：passed；
- Python Catalog 测试覆盖隐藏 Prompt/Secret、unknown 字段、hidden/unavailable Skill、未映射 Capability、签名认证和字段集合；
- Go 测试覆盖签名路径、未知字段严格拒绝、产品白名单、排序、畸形公开文案、unknown/unavailable 与上游失败不泄露；
- `cd frontend && npm test -- --run`：17 files / 62 tests passed；
- `cd frontend && npx tsc --noEmit`：passed；
- `cd frontend && npm run lint`：0 errors，保留 8 条既有 Fast Refresh warnings；
- `cd frontend && npm run build`：passed，保留既有 browserslist 与 bundle size warnings；
- `git diff --check`：passed。

## 未完成与风险

- 真实浏览器中的深链接、刷新、后退、Escape、焦点恢复、375/768/1024/1440 布局、网络失败和 Run 创建复校验进入 Round 唯一 E2E；
- 生产密钥、部署、Push、Skill Workbench 和个人 Skill 不在本 Task；
- 公开 Catalog 首版产品策略只允许 `research`、`fortune`，新增 Skill 必须同时经过 Manifest、公开 Capability 文案和 Go 产品白名单评审。

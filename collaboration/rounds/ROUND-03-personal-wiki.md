---
id: ROUND-03
title: 我的空间、Skills 与确认写入
status: in_progress
runtime_state: not_deployed
base_commit: c285fef00de10eccd042cb94313727fa5ba2c3bb
accepted_commit: pending
depends_on_rounds:
  - ROUND-02
tasks:
  - TASK-014
  - TASK-015
  - TASK-016
  - TASK-017
  - TASK-018
  - TASK-019
  - TASK-020
  - TASK-029
codex_round_e2e: required
user_gate: required
---

# ROUND-03：我的空间、Skills 与确认写入

## 业务结果

用户拥有一个可以长期增长的递归文档空间：从顶层文件夹逐层进入子目录，导入包含
嵌套结构的 Markdown 文件夹，阅读和管理文档。用户也可以查看真实可用 Skill 的公开
内容并直接带入对话，但本轮不编辑 Skill。

Agent 只使用符合状态和授权的最小个人上下文。AI 从文档提取的信息先成为 Proposal，
只有用户明确接受后才进入结构化事实；历史 Run 冻结实际使用的 Revision。

“我的空间”是用户入口，“Wiki Item”只作为 Go 拥有的结构化上下文模型存在，不建设
第二个与文档空间竞争的扁平一级页面。

## 产品边界

### 我的空间

- `/space` 只展示顶层文件夹；
- `/space/folders/:folderId` 只展示当前目录的直接子文件夹和直接子文档；
- 文件夹可递归嵌套，面包屑、刷新和浏览器前进/后退保持当前位置；
- 排序只有“最近打开”和“名称 A–Z”，文件夹始终在文件前；
- `/space/documents/:documentId` 展示 Markdown 正文和当前目录上下文；
- 桌面端复用 256px 工作区一级侧栏，文档页最多增加一个上下文栏；移动端使用抽屉或
  分层路由，不产生页面横向滚动；
- 根页不增加“最近打开”专区、全库文档表或全量展开树。

### 导入

- 支持单篇 Markdown，也支持选择整个文件夹并保留嵌套相对路径；
- 同名冲突、重复内容、非法路径、非 Markdown 文件、数量/大小上限和部分失败有明确
  预检与结果摘要；
- 不建立 Obsidian 实时同步，不保存本地绝对路径，不自动把原文写成 confirmed fact；
- 本轮的结构化提取仍以用户明确选择的一篇文档为单位，不自动批量消耗整库内容。

### Skills

- `/skills` 只展示服务端判定为当前用户有效且可见的真实 Skill；
- `/skills/:skillId` 提供可深链接的只读详情；
- 只展示标题、描述、版本、用途、公开 Capability、上下文范围和确认/写入规则；
- “在对话中使用”回到统一对话并预选该 Skill；
- 不提供内置 Skill 开关、卸载、编辑或发布，不泄露 Prompt、隐藏工作流和敏感配置。

## 主验收旅程

1. 登录后确认对话、Agent Runs、我的空间和 Skills 复用同一工作区外壳，账户位于左下；
2. 在“我的空间”创建顶层与嵌套文件夹，逐层进入并通过面包屑、后退、刷新恢复位置；
3. 在不同目录切换“最近打开”和“名称 A–Z”，确认只影响当前目录且文件夹优先；
4. 导入一个包含多层目录和多篇 Markdown 的求职文件夹，刷新后层级、原文和来源仍在；
5. 验证重复文件、同路径不同内容、非法路径、超限与不支持文件不会静默覆盖或半写入；
6. 打开、编辑、移动/重命名一篇文档，历史与当前路径可追溯；删除范围明确且不静默
   删除已确认的独立结构化事实；
7. 打开 Skills，查看 `research` 与 `fortune` 的真实公开详情，从详情进入对话并预选 Skill；
8. Agent 从用户明确选择的文档提取候选信息，但不直接写 confirmed Wiki；
9. 分别执行接受、修改后接受、暂缓和拒绝；重复提交、并发冲突和网络失败不产生半写入；
10. 发起对话并查看实际使用的 Context Item/Revision；outdated、rejected、forgotten 和
    未确认内容默认不进入 Context；
11. 修改当前信息后，历史 Run 仍引用当时 Revision；
12. 验证跨用户 Folder、Document、Wiki、Proposal 和 Context 访问被拒绝，Skills 路由
    只返回当前用户的 effective 公开投影。

## 必须回归

- ROUND-02 Direct/Research/Fortune、会话搜索、Agent Runs 与内部观测；
- Wiki/Document 不存在或 Context 为空时安全退化；
- 关闭 Context 注入后普通 Agent 仍能回答；
- Fortune narrative 不会自动写成 confirmed fact；
- Skills 目录与 `/` 菜单引用同一真实 Skill 可用性，不出现前端静态漂移；
- 375、768、1024、1440px 无页面横向溢出，键盘焦点与深链接可用。

## 能力控制与回滚

逻辑控制：

- `personal_space_enabled`；
- `document_import_enabled`；
- `wiki_context_injection_enabled`；
- `wiki_proposal_write_enabled`；
- `skill_catalog_enabled`。

这些是服务端权威的内部能力控制，不作为普通用户设置。关闭导入后保留已有空间只读/
管理能力；关闭 Context 注入后保留文档与确认信息管理；关闭 Proposal 写入后保留历史
Proposal 和 Revision；关闭 Skills 目录不影响对话中服务端仍允许的现有 Skill 执行。

回滚不删除 Folder、Document、DocumentRevision、Wiki、Revision、Source、Proposal 或
ContextUsage 数据，不执行破坏性 Schema 降级。上一轮统一 Agent 必须在新 Schema 保留
时继续工作。

## 完成标准

- 所有 Task `accepted`；
- 主验收旅程通过；
- ROUND-02 核心回归通过；
- 导入、Context 注入、Proposal 写入和 Skills 目录的停用边界分别演练；
- 关闭后用户数据和审计历史保持完整；
- 形成“能管理用户文档、理解用户上下文且能力透明”的稳定基线；
- 停止并等待用户是否进入 ROUND-04。

## 当前门禁

用户已于 2026-08-01 明确授权启动 ROUND-03。Solo 执行基线冻结为
`c285fef00de10eccd042cb94313727fa5ba2c3bb`，按 Task 依赖顺序连续实现；本授权不包含
push、部署、生产操作、破坏性 Migration 或进入 ROUND-04。

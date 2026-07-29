# Agent Runtime 上线、回滚与人工审核手册

> 更新日期：2026-07-29
>
> 适用变更：`codex/agent-runtime-migration`
>
> 当前状态：等待人工审核；本文不构成生产切换授权

## 1. 生产目标

最终生产组合：

```dotenv
AGENT_PROTOCOL_MODE=v1
AGENT_RUNTIME_STORE=postgres
AGENT_RUNTIME_COORDINATION=redis
AGENT_RUNTIME_CHECKPOINT_SETUP=false
```

Python 始终使用 `langgraph_v1`。Legacy 与 V1 是传输协议，不是两套 Agent。

生产切换必须使用固定镜像 tag/digest，不能使用浮动源码、未提交工作树或
`latest` 作为回滚基线。

## 2. 人工职责

必须由有权限的人确认或执行：

- 代码审核、提交拆分、合并与发布版本；
- 生产数据库备份和恢复抽查；
- 数据库角色、密码、grant 与 migration；
- Provider、HMAC、数据库和 Redis Secret 注入；
- 测试环境/小流量验收；
- 指标判断、扩量与最终生产授权。

自动化不得读取、打印或复制真实 Secret。

## 3. 发布前门禁

### 3.1 代码与构建

- [ ] 确认 diff 中没有真实 `.env`、Key、密码、Cookie 或采样内容。
- [ ] 确认旧 `backend/graph`、旧 RAG Agent、旧 requirements 未被重新加入。
- [ ] 确认 `pyproject.toml + uv.lock` 是唯一 Python 依赖来源。
- [ ] 确认 Python 和 Go 镜像使用不可变版本/digest。
- [ ] 记录待发布 commit SHA、镜像 digest 和上一稳定版本 digest。

仓库级发布提醒：2026-07-29 使用官方 npm audit endpoint 对前端生产依赖扫描时，
报告 11 项 advisory（9 high、2 moderate，均显示有可用修复）。这不是本轮 Agent
Runtime 迁移引入或修改的依赖，不能通过顺带运行 `npm audit fix` 在本迁移中盲改；
正式发布前应由前端依赖升级任务完成影响评估、升级与 UI 回归。

本地/CI 门禁：

```powershell
cd backend
uv lock --check
uv sync --frozen --group target-test --python 3.11
uv run pytest tests/unit -q
uvx ruff check agent app tests scripts

cd ../go-backend
go test ./...

cd ..
git diff --check
docker compose -f docker-compose.yml config --quiet
```

真实 PostgreSQL 集成测试只在隔离测试库执行：

```powershell
cd backend
$env:TEST_DATABASE_URL = "<隔离测试库连接>"
uv run pytest tests/integration/test_postgres_runtime_store.py -q
Remove-Item Env:TEST_DATABASE_URL
```

### 3.2 数据与容量

- [ ] 确认 PostgreSQL 15+ 可用。
- [ ] 确认 Redis 7 可用；Redis 故障不会影响 PostgreSQL 事实。
- [ ] 评估 `agent_runtime` 短期 Event/Artifact/Checkpoint 增长。
- [ ] 确认 retention 与备份保留策略。
- [ ] 确认数据库连接池总量适合计划副本数。
- [ ] 单副本 `memory` 阶段不得提前扩容 Python。

## 4. 数据库准备

### 4.1 备份

先按团队标准做完整生产备份并记录备份 ID。若使用 PostgreSQL 原生命令，可由 DBA
在安全终端执行：

```powershell
pg_dump --format=custom --file "<安全备份路径>" "$env:MIGRATION_DATABASE_URL"
pg_restore --list "<安全备份路径>"
```

至少抽查备份可读取；高风险环境应在隔离实例完成恢复演练。

### 4.2 Go schema migration

迁移 `005_agent_runtime_foundation.sql` 是增量建 schema/table/index，不删除业务表。
新镜像内提供一次性 migration binary：

```powershell
docker compose build gateway
docker compose run --rm --no-deps --entrypoint /app/qidian-migrate gateway
```

命令使用 `GO_DATABASE_URL`、`DATABASE_URL` 或 `POSTGRES_*`，通过 advisory lock 和
`go_schema_migrations` 保证串行、幂等执行。执行后由 DBA 确认：

- `agent_runtime.runtime_executions`
- `agent_runtime.runtime_events`
- `agent_runtime.runtime_artifacts`
- `public.go_schema_migrations` 已记录 `005_agent_runtime_foundation.sql`

### 4.3 Checkpoint schema

Checkpoint 建表必须是独立部署步骤，生产 Web 进程保持：

```dotenv
AGENT_RUNTIME_CHECKPOINT_SETUP=false
```

用具备 `agent_runtime` schema 建表权限的部署连接执行：

```powershell
docker compose build python
docker compose run --rm --no-deps `
  --entrypoint python `
  python scripts/setup_agent_runtime.py
```

成功输出只能说明 schema ready，不应包含连接串或凭据。确认以下表存在：

- `agent_runtime.checkpoint_migrations`
- `agent_runtime.checkpoints`
- `agent_runtime.checkpoint_blobs`
- `agent_runtime.checkpoint_writes`

### 4.4 最小权限

推荐区分：

- `app_core` owner/migration role：Go schema migration；
- `agent_runtime` deploy role：Checkpoint schema 升级；
- Python runtime role：只连接数据库并读写 `agent_runtime` 现有对象；
- Go app role：只读写 `app_core` 和产品观测表，不依赖 Runtime 表。

具体角色名和 Secret 由 DBA 决定。Checkpoint setup 后，Python runtime role 至少需要：

```sql
GRANT CONNECT ON DATABASE <database> TO <runtime_role>;
GRANT USAGE ON SCHEMA agent_runtime TO <runtime_role>;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA agent_runtime TO <runtime_role>;
GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA agent_runtime TO <runtime_role>;
```

若 deploy role 与 runtime role 分离，不要给 runtime role `CREATE` 或业务 schema
权限。每次 Checkpoint 库升级后由 deploy role 重新执行 setup，并复核新对象 grant。

## 5. 分阶段切换

每一步单独部署、观察并保留回滚点，不同时改变协议、持久化和副本数。

### 阶段 A：测试环境全组合

在非生产环境启用：

```dotenv
AGENT_PROTOCOL_MODE=v1
AGENT_RUNTIME_STORE=postgres
AGENT_RUNTIME_COORDINATION=redis
```

验证 Chat、Research、Fortune、显式停止、浏览器刷新/断开、同一 execution 重附着、
服务重启、Redis 暂停与 PostgreSQL lease 接管。

### 阶段 B：生产新镜像，保守配置

先部署新镜像但保持：

```dotenv
AGENT_PROTOCOL_MODE=legacy
AGENT_RUNTIME_STORE=memory
AGENT_RUNTIME_COORDINATION=none
```

此阶段 Python 只能单副本。验证健康、三类工作流、回答落库和错误率。需要回滚 Agent
行为时使用上一稳定镜像；不要恢复已经删除的第二套 Graph 到新镜像。

### 阶段 C：启用持久 Runtime

保持 Go `legacy`，只切：

```dotenv
AGENT_RUNTIME_STORE=postgres
AGENT_RUNTIME_COORDINATION=redis
```

确认 readiness、Event 回放、Checkpoint、retention 与 Redis fail-open。稳定后才允许
增加 Python 副本。

### 阶段 D：切换 V1

最后切：

```dotenv
AGENT_PROTOCOL_MODE=v1
```

先小流量/单可用区，再逐步扩量。不得用真实用户流量做未告知的内容采样。

## 6. 每阶段观测

至少观察一个完整业务高峰或团队规定窗口：

- 请求成功率、首 token 和总耗时；
- `completed / cancelled / failed / timed_out` 比例；
- `agent_event_sequence_gap`；
- `runtime.recovery_failed`、lease lost 与 takeover 次数；
- 同一 execution 的重复终态、重复答案或不连续 sequence；
- 浏览器断开后的后台完成率；
- 显式停止延迟；
- PostgreSQL 连接数、锁等待、表/索引增长；
- Redis 错误与 PostgreSQL polling 后备延迟；
- Model/Tool 错误、token 和成本；
- Go 产品 Run 与 Python Runtime Run 的终态不一致。

任何 Secret、完整 Prompt、用户内容或模型隐式思维链都不应出现在日志和 Trace 中。

## 7. 回滚

优先使用最小范围回滚：

1. V1 传输问题：将 `AGENT_PROTOCOL_MODE` 改回 `legacy`。
2. Redis 问题：将 `AGENT_RUNTIME_COORDINATION` 改为 `none`，保留 PostgreSQL。
3. PostgreSQL Runtime 问题：先停止新流量并等待/收口活跃 execution，再在单 Python
   副本下改回 `memory`。
4. Graph、模型或能力行为问题：回滚到记录好的上一稳定镜像 digest。

注意：

- 不要在事故处理中删除 `agent_runtime` schema 或回退 migration 005；它是增量对象，
  旧镜像可忽略。
- 不要在仍有活跃 execution 时从 PostgreSQL 直接切到 memory，否则重附着和恢复会
  丢失事实源。
- 不要把浏览器断开当作批量取消手段。
- 回滚镜像前保留运行快照、错误码和脱敏事件，供事后分析。
- 若数据库本身损坏，按已验证的团队恢复流程恢复完整备份，不在现场即兴执行
  destructive SQL。

## 8. 最终人工批准

只有以下项目全部勾选才能把 V1 设为生产默认：

- [ ] 两名或团队规定数量的代码审核者批准。
- [ ] 迁移与 Checkpoint schema 已由 DBA 确认。
- [ ] 备份 ID、恢复抽查和上一镜像 digest 已记录。
- [ ] 测试环境强杀、断网、Redis 故障和显式取消通过。
- [ ] 生产阶段 B/C 观察窗口通过。
- [ ] V1 小流量指标与 Legacy 基线无不可接受回归。
- [ ] 告警、值班人、回滚执行人和决策人明确。
- [ ] Secret 仅通过生产 Secret 管理系统注入。
- [ ] 最终变更窗口获得授权。

批准后才将生产默认设置为 `v1 + postgres + redis`。迁移完成不等于产品后续的命理
知识、认知镜像、决策和复盘功能已经完成。

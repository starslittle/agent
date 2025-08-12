# Restructure Plan (apps/libs/workers)

本次迁移为“增量引入、保持可运行”：

1) 新增 `apps/api/__init__.py` 复用现有 `backend.main:app`；
2) 新增 `apps/workers/` 作为异步/入库任务占位；
3) 新增 `libs/rag_core/` 暴露 `query()` 接口，内部临时复用 `backend/agent_factory.py` 与 `backend/agents.yaml`；

后续步骤：
- 将 `src/rag` 能力逐步迁入 `libs/rag_core`（engines/retriever/ingest）；
- `apps/api` 的路由逐步改为仅调用 `libs/rag_core`，避免直接 import backend.*；
- 清理 `sys.path` hack，改为包导入；
- 为 `libs/rag_core` 增加单元测试与 CI；

当前不影响原有启动方式：
- 后端：`uvicorn backend.main:app`；
- 前端：`npm run dev`；



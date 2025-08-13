# Restructure Plan (apps/libs/workers)

本次迁移为“增量引入、保持可运行”：

1) 现已完成迁移至 `src/api/main.py:app`；
2) 新增 `apps/workers/` 作为异步/入库任务占位；
3) 新增 `libs/rag_core/` 暴露 `query()` 接口，内部改为使用 `src.api.agent_factory` 与 `configs/agents.yaml`；

后续步骤：
- 将 `src/rag` 能力逐步迁入 `libs/rag_core`（engines/retriever/ingest）；
- API 路由改为仅调用 `libs/rag_core` 或 `src/rag`，不再 import 旧 backend；
- 清理 `sys.path` hack，改为包导入；
- 为 `libs/rag_core` 增加单元测试与 CI；

当前不影响原有启动方式：
- 后端：`uvicorn src.api.main:app`；
- 前端：`npm run dev`；

命理库入库（最小流程）：
```
pip install python-docx langchain-community chromadb sentence-transformers
python apps/workers/ingest_fortune.py
```



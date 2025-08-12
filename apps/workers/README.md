# Workers

占位目录：用于承载离线/异步任务（文档入库、索引刷新、评估等）。

后续建议：
- `ingest.py`：从 `data/`、对象存储或消息队列读取文档，调用 libs/rag_core.ingest。
- `schedules.py`：定时刷新/重建索引（cron/apscheduler）。



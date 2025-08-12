"""
API 应用包。当前阶段复用现有 `backend.main:app`，便于平滑迁移。

后续可将路由拆分至 `routers/`，由此处统一导出 FastAPI `app`。
"""

from backend.main import app  # noqa: F401



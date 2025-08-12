"""轻薄封装层：对现有 src/rag 能力做稳定接口的导出。

目标：
- 提供 query/ingest 等用例级 API，隐藏底层实现与依赖；
- apps/api 与 apps/workers 仅依赖这里，不直接 import src.rag；
"""

from .pipelines import query  # noqa: F401



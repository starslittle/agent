from typing import Optional

from llama_index.core.base.base_query_engine import BaseQueryEngine


class RAGEngine:
    """RAG 引擎抽象基类。

    子类应实现：
    - name: 内部名称（用于 get_query_engine）
    - tool_name: 暴露为工具时的名称
    - description: 工具描述
    - build(): 返回 BaseQueryEngine 或 None
    """

    name: str
    tool_name: str
    description: str

    def __init__(self, config):
        self.config = config

    def build(self) -> Optional[BaseQueryEngine]:  # pragma: no cover - 接口定义
        raise NotImplementedError



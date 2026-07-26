"""Tool package.

Tools are loaded lazily through ``agent.tools.registry`` so importing the Agent
Service no longer initializes Pandas, Chroma, or local RAG dependencies.
"""

from .registry import ToolDefinition, ToolRegistry, get_tool_registry

_LAZY_EXPORTS = {
    "get_current_date": ("agent.tools.date", "get_current_date"),
    "get_seniverse_weather": ("agent.tools.weather", "get_seniverse_weather"),
    "get_lunar_chart": ("agent.tools.lunar_chart", "get_lunar_chart"),
    "get_ziwei_chart": ("agent.tools.ziwei_chart", "get_ziwei_chart"),
    "init_pandas_rag": ("agent.tools.pandas_kb", "init_pandas_rag"),
    "query_pandas_data": ("agent.tools.pandas_kb", "query_pandas_data"),
    "init_local_rag": ("agent.tools.local_kb", "init_local_rag"),
    "query_local_kb": ("agent.tools.local_kb", "query_local_kb"),
    "deep_research": ("agent.tools.deep_research", "deep_research"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    from importlib import import_module

    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


__all__ = [
    "ToolDefinition",
    "ToolRegistry",
    "get_tool_registry",
    *_LAZY_EXPORTS,
]

"""Tool package.

Tools are loaded lazily through ``agent.tools.registry`` so importing the Agent
Service no longer initializes Pandas, Chroma, or local RAG dependencies.
"""

from .registry import ToolDefinition, ToolRegistry, get_tool_registry

_LAZY_EXPORTS = {
    "get_current_date": ("agent.tools.date", "get_current_date"),
    "get_lunar_chart": ("agent.tools.lunar_chart", "get_lunar_chart"),
    "get_ziwei_chart": ("agent.tools.ziwei_chart", "get_ziwei_chart"),
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

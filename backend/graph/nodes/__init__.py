"""Graph node package with lazy compatibility exports.

The public streaming path imports only router/planner/executor/replanner/generate.
Keeping every historical node eager here would also load disabled RAG, Pandas and
Chroma dependencies during an ordinary Agent Service startup.
"""

from importlib import import_module


_EXPORTS = {
    "router_node": ("graph.nodes.router", "router_node"),
    "direct_llm_node": ("graph.nodes.direct_llm", "direct_llm_node"),
    "tool_router_node": ("graph.nodes.tool_router", "tool_router_node"),
    "tools_node": ("graph.nodes.tools_exec", "tools_node"),
    "rag_node": ("graph.nodes.rag", "rag_node"),
    "retrieval_node": ("graph.nodes.retrieval", "retrieval_node"),
    "generate_node": ("graph.nodes.generate", "generate_node"),
    "generation_node": ("graph.nodes.generation", "generation_node"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value

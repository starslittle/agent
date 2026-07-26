"""API package with lazy compatibility exports.

Importing ``app.api.agent_runs`` must not eagerly construct legacy Agent/RAG
dependencies.  Legacy callers can keep using the historical package exports,
which are loaded only when actually requested.
"""

from importlib import import_module


__all__ = ["create_agent_from_config", "classify_and_route", "get_intent_router"]

_EXPORTS = {
    "create_agent_from_config": ("app.api.agent_factory", "create_agent_from_config"),
    "classify_and_route": ("app.api.intent_router", "classify_and_route"),
    "get_intent_router": ("app.api.intent_router", "get_intent_router"),
}


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer


def emit_runtime_event(event_type: str, **data: Any) -> None:
    """Emit one provider-neutral event on LangGraph's custom stream."""
    writer = get_stream_writer()
    writer({"type": event_type, "data": data})


def emit_capability_event(
    event_type: str,
    data: dict[str, Any],
) -> None:
    emit_runtime_event(event_type, **data)


def emit_model_event(
    event_type: str,
    data: dict[str, Any],
) -> None:
    emit_runtime_event(event_type, **data)

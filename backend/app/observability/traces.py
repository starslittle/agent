from __future__ import annotations

import secrets
import time
from typing import Any

from .redaction import sanitize_event_data


def new_span_id() -> str:
    return secrets.token_hex(8)


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def extract_model_usage(response: Any) -> dict[str, int]:
    usage: dict[str, Any] = {}
    for candidate in (
        getattr(response, "usage_metadata", None),
        getattr(response, "response_metadata", None),
    ):
        if not isinstance(candidate, dict):
            continue
        nested = (
            candidate.get("token_usage")
            or candidate.get("usage")
            or candidate
        )
        if isinstance(nested, dict):
            usage.update(nested)
    input_tokens = _integer(
        usage.get("input_tokens")
        or usage.get("prompt_tokens")
        or usage.get("inputTokens")
    )
    output_tokens = _integer(
        usage.get("output_tokens")
        or usage.get("completion_tokens")
        or usage.get("outputTokens")
    )
    cached_tokens = _integer(
        usage.get("cached_tokens")
        or usage.get("cache_read_input_tokens")
    )
    total_tokens = _integer(usage.get("total_tokens")) or (
        input_tokens + output_tokens
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_tokens": cached_tokens,
        "total_tokens": total_tokens,
    }


def build_model_trace(
    *,
    stage: str,
    model_name: str,
    started_at: float,
    response: Any | None = None,
    status: str = "completed",
    error_code: str = "",
    iteration: int | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "span_id": span_id or new_span_id(),
        "span_type": "model",
        "stage": stage,
        "name": model_name,
        "provider": "dashscope",
        "status": status,
        "duration_ms": max(0, int((time.perf_counter() - started_at) * 1000)),
        "content_capture_level": "hashed",
        **extract_model_usage(response),
    }
    if error_code:
        trace["error_code"] = error_code[:128]
    if iteration is not None:
        trace["iteration"] = iteration
    return sanitize_event_data(trace)


def append_model_trace(
    state: dict[str, Any],
    trace: dict[str, Any],
) -> dict[str, Any]:
    metadata = dict(state.get("metadata") or {})
    traces = list(metadata.get("model_traces") or [])
    traces.append(trace)
    metadata["model_traces"] = traces
    return {**state, "metadata": metadata}

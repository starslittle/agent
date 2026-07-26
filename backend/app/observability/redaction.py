from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_SENSITIVE_KEY = re.compile(
    r"(authorization|cookie|password|passwd|secret|api[_-]?key|"
    r"database[_-]?url|connection[_-]?string|"
    r"(?:^|[_-])token(?:$|[_-])|"
    r"(?:access|refresh|auth|session|bearer|id)[_-]?token)",
    re.IGNORECASE,
)
_SENSITIVE_VALUES = (
    (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
        "Bearer [redacted]",
    ),
    (
        re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{8,})\b"),
        "[redacted-api-key]",
    ),
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^:/\s]+):[^@\s]+@"),
        r"\1:[redacted]@",
    ),
    (
        re.compile(
            r"(?i)([?&](?:api[_-]?key|token|secret|password)=)[^&\s]+"
        ),
        r"\1[redacted]",
    ),
)


def _encoded(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def payload_fingerprint(value: Any) -> dict[str, Any]:
    """Describe content without retaining the content itself."""
    encoded = _encoded(value)
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "kind": type(value).__name__,
    }


def sanitize_event_data(
    value: Any,
    *,
    max_string_chars: int = 500,
    max_depth: int = 5,
) -> Any:
    """Apply a final defensive redaction before an event leaves Python."""

    def walk(item: Any, depth: int) -> Any:
        if depth > max_depth:
            return "[depth-limited]"
        if isinstance(item, dict):
            clean: dict[str, Any] = {}
            for raw_key, child in item.items():
                key = str(raw_key)
                clean[key] = (
                    "[redacted]"
                    if _SENSITIVE_KEY.search(key)
                    else walk(child, depth + 1)
                )
            return clean
        if isinstance(item, (list, tuple)):
            return [walk(child, depth + 1) for child in item[:100]]
        if isinstance(item, str):
            for pattern, replacement in _SENSITIVE_VALUES:
                item = pattern.sub(replacement, item)
            if len(item) <= max_string_chars:
                return item
            return item[:max_string_chars] + "…"
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return walk(str(item), depth + 1)

    return walk(value, 0)

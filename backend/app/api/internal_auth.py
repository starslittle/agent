"""Verify signed requests sent by the Go application backend."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from app.core.settings import settings


_MAX_CLOCK_SKEW_SECONDS = 90


@dataclass
class _NonceEntry:
    expires_at: float


class _NonceCache:
    def __init__(self) -> None:
        self._entries: dict[str, _NonceEntry] = {}
        self._lock = threading.Lock()

    def consume(self, nonce: str, ttl_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            expired = [
                key for key, entry in self._entries.items() if entry.expires_at <= now
            ]
            for key in expired:
                self._entries.pop(key, None)
            if nonce in self._entries:
                return False
            self._entries[nonce] = _NonceEntry(now + ttl_seconds)
            return True


_NONCES = _NonceCache()


def verify_internal_request(
    headers: Mapping[str, str],
    body: bytes,
    *,
    method: str = "POST",
    path: str = "/query_stream",
    execution_id: str = "",
) -> bool:
    secret = settings.INTERNAL_AGENT_SECRET
    user_id = headers.get("x-qidian-user-id", "").strip()
    request_id = headers.get("x-request-id", "").strip()
    timestamp = headers.get("x-qidian-timestamp", "").strip()
    signature = headers.get("x-qidian-signature", "").strip().lower()
    signature_version = headers.get("x-qidian-signature-version", "").strip()

    if len(secret) < 32 or not all((user_id, request_id, timestamp, signature)):
        return False

    try:
        request_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if request_time.tzinfo is None:
            return False
        age = abs((datetime.now(timezone.utc) - request_time).total_seconds())
        if age > _MAX_CLOCK_SKEW_SECONDS:
            return False
    except (TypeError, ValueError):
        return False

    body_hash = hashlib.sha256(body).hexdigest()
    if signature_version == "v1":
        signed_execution_id = headers.get("x-qidian-execution-id", "").strip()
        nonce = headers.get("x-qidian-nonce", "").strip()
        if (
            not signed_execution_id
            or signed_execution_id != execution_id
            or len(nonce) < 16
        ):
            return False
        canonical = "\n".join(
            (
                "1",
                method.upper(),
                path,
                user_id,
                signed_execution_id,
                request_id,
                timestamp,
                nonce,
                body_hash,
            )
        )
    else:
        # Legacy signature remains valid only for the compatibility endpoint.
        if method.upper() != "POST" or path != "/query_stream":
            return False
        canonical = "\n".join((user_id, request_id, timestamp, body_hash))
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False
    if signature_version == "v1":
        return _NONCES.consume(nonce, _MAX_CLOCK_SKEW_SECONDS * 2)
    return True

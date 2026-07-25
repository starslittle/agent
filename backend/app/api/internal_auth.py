"""Verify signed requests sent by the Go application backend."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import Mapping

from app.core.settings import settings


_MAX_CLOCK_SKEW_SECONDS = 90


def verify_internal_request(headers: Mapping[str, str], body: bytes) -> bool:
    secret = settings.INTERNAL_AGENT_SECRET
    user_id = headers.get("x-qidian-user-id", "").strip()
    request_id = headers.get("x-request-id", "").strip()
    timestamp = headers.get("x-qidian-timestamp", "").strip()
    signature = headers.get("x-qidian-signature", "").strip().lower()

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
    canonical = "\n".join((user_id, request_id, timestamp, body_hash))
    expected = hmac.new(
        secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

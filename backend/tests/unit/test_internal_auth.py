from datetime import datetime, timezone
import hashlib
import hmac

from app.api import internal_auth


def test_verify_internal_request(monkeypatch):
    secret = "test-secret-that-is-at-least-32-characters"
    monkeypatch.setattr(internal_auth.settings, "INTERNAL_AGENT_SECRET", secret)
    body = b'{"query":"hello"}'
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    user_id = "user-1"
    request_id = "request-1"
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join((user_id, request_id, timestamp, body_hash))
    signature = hmac.new(
        secret.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "x-qidian-user-id": user_id,
        "x-request-id": request_id,
        "x-qidian-timestamp": timestamp,
        "x-qidian-signature": signature,
    }

    assert internal_auth.verify_internal_request(headers, body)
    assert not internal_auth.verify_internal_request(headers, body + b" ")

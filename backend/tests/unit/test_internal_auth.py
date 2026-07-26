from datetime import datetime, timezone
import hashlib
import hmac
import uuid

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


def test_verify_v1_signature_binds_method_path_execution_and_nonce(monkeypatch):
    secret = "test-secret-that-is-at-least-32-characters"
    monkeypatch.setattr(internal_auth.settings, "INTERNAL_AGENT_SECRET", secret)
    body = b'{"execution_id":"exec-1"}'
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    nonce = uuid.uuid4().hex
    values = (
        "1",
        "POST",
        "/internal/v1/agent-runs:stream",
        "user-1",
        "exec-1",
        "request-1",
        timestamp,
        nonce,
        hashlib.sha256(body).hexdigest(),
    )
    signature = hmac.new(
        secret.encode(),
        "\n".join(values).encode(),
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "x-qidian-signature-version": "v1",
        "x-qidian-user-id": "user-1",
        "x-qidian-execution-id": "exec-1",
        "x-request-id": "request-1",
        "x-qidian-timestamp": timestamp,
        "x-qidian-nonce": nonce,
        "x-qidian-signature": signature,
    }
    assert internal_auth.verify_internal_request(
        headers,
        body,
        method="POST",
        path="/internal/v1/agent-runs:stream",
        execution_id="exec-1",
    )
    # A consumed nonce cannot be replayed inside the accepted clock window.
    assert not internal_auth.verify_internal_request(
        headers,
        body,
        method="POST",
        path="/internal/v1/agent-runs:stream",
        execution_id="exec-1",
    )
    assert not internal_auth.verify_internal_request(
        {**headers, "x-qidian-nonce": uuid.uuid4().hex},
        body,
        method="DELETE",
        path="/internal/v1/agent-runs/exec-1",
        execution_id="exec-1",
    )

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agent_runs
from app.runtime.registry import ExecutionRegistry


SECRET = "test-secret-that-is-at-least-32-characters"


def _headers(method: str, path: str, execution_id: str, body: bytes) -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    nonce = uuid.uuid4().hex
    request_id = uuid.uuid4().hex
    canonical = "\n".join(
        (
            "1",
            method,
            path,
            "user-1",
            execution_id,
            request_id,
            timestamp,
            nonce,
            hashlib.sha256(body).hexdigest(),
        )
    )
    signature = hmac.new(
        SECRET.encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return {
        "content-type": "application/json",
        "x-qidian-signature-version": "v1",
        "x-qidian-user-id": "user-1",
        "x-qidian-execution-id": execution_id,
        "x-request-id": request_id,
        "x-qidian-timestamp": timestamp,
        "x-qidian-nonce": nonce,
        "x-qidian-signature": signature,
    }


def test_v1_stream_and_status_api(monkeypatch):
    class FakeRuntime:
        async def stream(self, request, cancel_event):
            yield "route.selected", {"actual_route": "default"}
            yield "answer.delta", {"text": "hello"}

        async def cancel(self, execution_id):
            return None

    monkeypatch.setattr(agent_runs.settings, "INTERNAL_AGENT_SECRET", SECRET)
    monkeypatch.setattr(
        agent_runs,
        "registry",
        ExecutionRegistry(FakeRuntime(), service_version="test"),
    )
    app = FastAPI()
    app.include_router(agent_runs.router)
    client = TestClient(app)

    payload = {
        "protocol_version": 1,
        "execution_id": "exec-api-1",
        "run_id": "run-api-1",
        "request_id": "req-api-1",
        "idempotency_key": "idem-api-1",
        "conversation_id": "conv-api-1",
        "agent_name": "default_llm_agent",
        "query": "hello",
        "messages": [],
        "deadline_ms": 5000,
        "shadow": False,
        "metadata": {},
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    path = "/internal/v1/agent-runs:stream"
    response = client.post(
        path,
        content=body,
        headers=_headers("POST", path, payload["execution_id"], body),
    )
    assert response.status_code == 200
    assert "event: run.started" in response.text
    assert "event: run.resolved" in response.text
    assert "id: exec-api-1:2" in response.text
    assert "event: run.completed" in response.text

    status_path = "/internal/v1/agent-runs/exec-api-1"
    status = client.get(
        status_path,
        headers=_headers("GET", status_path, payload["execution_id"], b""),
    )
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["last_sequence"] == 5

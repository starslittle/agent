from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
from types import SimpleNamespace
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import agent_runs
from agent.skills import get_skill_registry, public_skill_catalog


SECRET = "test-secret-that-is-at-least-32-characters"


def _headers() -> dict[str, str]:
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    nonce = uuid.uuid4().hex
    request_id = uuid.uuid4().hex
    canonical = "\n".join(("1", "GET", "/internal/v1/skills", "user-1", "skill-catalog", request_id, timestamp, nonce, hashlib.sha256(b"").hexdigest()))
    signature = hmac.new(SECRET.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return {
        "x-qidian-signature-version": "v1",
        "x-qidian-user-id": "user-1",
        "x-qidian-execution-id": "skill-catalog",
        "x-request-id": request_id,
        "x-qidian-timestamp": timestamp,
        "x-qidian-nonce": nonce,
        "x-qidian-signature": signature,
    }


def test_public_catalog_contains_only_explicit_browser_fields():
    catalog = public_skill_catalog(get_skill_registry())

    assert [item.id for item in catalog] == ["fortune", "research"]
    encoded = [item.model_dump(mode="json") for item in catalog]
    assert set(encoded[0]) == {
        "id",
        "version",
        "title",
        "description",
        "command",
        "public_purpose",
        "public_capabilities",
        "context_scope",
        "confirmation_summary",
        "may_propose_updates",
        "available",
        "effective",
    }
    serialized = repr(encoded).lower()
    for forbidden in ("workflow", "prompt", "schema", "budget", "secret", "tool_calling"):
        assert forbidden not in serialized
    assert all(set(capability) == {"label", "description"} for item in encoded for capability in item["public_capabilities"])
    assert all(set(scope) == {"label"} for item in encoded for scope in item["context_scope"])


def test_public_catalog_hides_unavailable_hidden_and_unmapped_entries():
    source = get_skill_registry().resolve("research")
    visible = deepcopy(source)
    visible.__dict__["system_prompt"] = "never expose this"
    visible.__dict__["provider_api_key"] = "secret"
    unavailable = deepcopy(source)
    unavailable.id = "unavailable"
    unavailable.available = False
    hidden = deepcopy(source)
    hidden.id = "hidden"
    hidden.ui.visible = False
    unmapped = deepcopy(source)
    unmapped.id = "unmapped"
    unmapped.allowed_capabilities = ["new_internal_capability"]
    registry = SimpleNamespace(available=lambda: [visible, unavailable, hidden, unmapped])

    catalog = public_skill_catalog(registry)

    assert [item.id for item in catalog] == ["research"]
    assert "never expose this" not in repr(catalog)
    assert "secret" not in repr(catalog)


def test_internal_skill_catalog_requires_signature_and_returns_safe_projection(monkeypatch):
    monkeypatch.setattr(agent_runs.settings, "INTERNAL_AGENT_SECRET", SECRET)
    monkeypatch.setattr(agent_runs.settings, "DASHSCOPE_API_KEY", "model-key")
    monkeypatch.setattr(agent_runs.settings, "TAVILY_API_KEY", "search-key")
    app = FastAPI()
    app.include_router(agent_runs.router)
    client = TestClient(app)

    assert client.get("/internal/v1/skills").status_code == 401
    response = client.get("/internal/v1/skills", headers=_headers())

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["fortune", "research"]
    serialized = response.text.lower()
    assert "workflow" not in serialized
    assert "prompt" not in serialized
    assert "secret" not in serialized

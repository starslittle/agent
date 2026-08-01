from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agent.models import (
    ModelCapabilities,
    ModelProfile,
    UnknownModelIDError,
    get_model_catalog,
    load_model_catalog,
)
from agent.readiness import validate_target_runtime


def _profiles(provider: str = "test_provider") -> list[ModelProfile]:
    return [
        ModelProfile(
            name="default_chat",
            provider=provider,
            model="test-model-v1",
            temperature=0.2,
            timeout_seconds=30,
            max_retries=2,
            capabilities=ModelCapabilities(
                streaming=True,
                tool_calling=True,
                json_mode=True,
            ),
        )
    ]


def _document() -> dict:
    return {
        "default_model_id": "auto",
        "models": [
            {"id": "auto", "profile": "default_chat", "available": True}
        ],
    }


def _load(
    tmp_path: Path,
    document: object,
    *,
    profiles: list[ModelProfile] | None = None,
    providers: set[str] | None = None,
):
    path = tmp_path / "models.yaml"
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load_model_catalog(
        path=path,
        profiles=profiles or _profiles(),
        providers=providers or {"test_provider"},
    )


def test_auto_resolves_to_stable_controlled_snapshot():
    catalog = get_model_catalog()
    first = catalog.resolve("auto")
    second = catalog.resolve(None)

    assert first.model_id == "auto"
    assert first.profile == "default_chat"
    assert first.provider
    assert first.model
    assert first.capabilities.streaming is True
    assert first == second
    assert len(first.fingerprint) == 64
    assert catalog.ids(available_only=True) == ["auto"]
    assert catalog.fingerprint() == get_model_catalog().fingerprint()


def test_unknown_model_id_uses_stable_error():
    with pytest.raises(UnknownModelIDError) as captured:
        get_model_catalog().resolve("provider/model-from-user")

    assert captured.value.code == "unknown_model_id"
    assert captured.value.model_id == "provider/model-from-user"


def test_unknown_profile_fails_at_catalog_construction(tmp_path: Path):
    document = _document()
    document["models"][0]["profile"] = "missing"

    with pytest.raises(ValueError, match="unknown profile"):
        _load(tmp_path, document)


def test_unknown_provider_fails_at_catalog_construction(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown provider"):
        _load(tmp_path, _document(), providers={"another_provider"})


def test_duplicate_and_invalid_default_fail(tmp_path: Path):
    duplicate = _document()
    duplicate["models"].append(deepcopy(duplicate["models"][0]))
    with pytest.raises(ValueError, match="unique"):
        _load(tmp_path, duplicate)

    missing = _document()
    missing["default_model_id"] = "missing"
    with pytest.raises(ValueError, match="default model_id must exist"):
        _load(tmp_path, missing)

    unavailable = _document()
    unavailable["models"][0]["available"] = False
    with pytest.raises(ValueError, match="must be available"):
        _load(tmp_path, unavailable)


def test_unknown_config_fields_and_secret_like_fields_fail(tmp_path: Path):
    document = _document()
    document["models"][0]["api_key"] = "must-not-be-configurable"

    with pytest.raises(ValidationError):
        _load(tmp_path, document)


def test_snapshot_and_fingerprint_do_not_contain_provider_credentials(
    tmp_path: Path,
):
    document = _document()
    catalog = _load(tmp_path, document)
    snapshot = catalog.resolve("auto").model_dump(mode="json")

    assert set(snapshot) == {
        "model_id",
        "profile",
        "provider",
        "model",
        "capabilities",
        "temperature",
        "timeout_seconds",
        "max_retries",
        "fingerprint",
    }
    assert "api_key" not in str(snapshot).lower()
    assert "base_url" not in str(snapshot).lower()


def test_readiness_includes_validated_model_catalog():
    report = validate_target_runtime()

    assert report["model_ids"] == ["auto"]
    assert len(report["model_catalog_fingerprint"]) == 64

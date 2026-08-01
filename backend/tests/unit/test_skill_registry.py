from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from agent.skills import get_skill_registry, load_skill_registry


WORKFLOWS = {"research_v1", "fortune_v1"}
CAPABILITIES = {
    "tavily_search",
    "web_search",
    "get_weather",
    "get_current_date",
    "get_lunar_chart",
    "get_ziwei_chart",
}


def _valid_document() -> dict:
    registry = get_skill_registry()
    return {
        "skills": [
            registry.resolve(skill_id).model_dump(mode="json")
            for skill_id in registry.ids()
        ]
    }


def _load(tmp_path: Path, document: object):
    path = tmp_path / "skills.yaml"
    path.write_text(
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return load_skill_registry(
        path=path,
        workflows=WORKFLOWS,
        capabilities=CAPABILITIES,
    )


def test_registry_loads_research_and_fortune_with_stable_fingerprint():
    first = get_skill_registry()
    second = load_skill_registry()

    assert first.ids() == ["fortune", "research"]
    assert [item.id for item in first.available()] == ["fortune", "research"]
    assert first.resolve("research").workflow == "research_v1"
    assert first.resolve("fortune").allowed_capabilities == [
        "get_current_date",
        "get_lunar_chart",
        "get_ziwei_chart",
    ]
    assert first.fingerprint() == second.fingerprint()
    assert len(first.fingerprint()) == 64


def test_duplicate_skill_id_fails(tmp_path: Path):
    document = _valid_document()
    document["skills"].append(deepcopy(document["skills"][0]))

    with pytest.raises(ValueError, match="unique"):
        _load(tmp_path, document)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("workflow", "missing_v1", "unknown workflow"),
        ("allowed_capabilities", ["missing_tool"], "unknown capabilities"),
    ],
)
def test_unknown_references_fail(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
):
    document = _valid_document()
    document["skills"][0][field] = value

    with pytest.raises(ValueError, match=error):
        _load(tmp_path, document)


@pytest.mark.parametrize("version", [0, -1])
def test_invalid_version_fails(tmp_path: Path, version: int):
    document = _valid_document()
    document["skills"][0]["version"] = version

    with pytest.raises(ValidationError):
        _load(tmp_path, document)


def test_extra_field_fails(tmp_path: Path):
    document = _valid_document()
    document["skills"][0]["provider_api_key"] = "must-not-exist"

    with pytest.raises(ValidationError):
        _load(tmp_path, document)


def test_unavailable_skill_is_not_listed(tmp_path: Path):
    document = _valid_document()
    document["skills"][0]["available"] = False
    registry = _load(tmp_path, document)

    assert registry.ids() == ["fortune", "research"]
    assert [item.id for item in registry.available()] == ["research"]


def test_missing_or_invalid_config_fails(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_skill_registry(path=tmp_path / "missing.yaml")

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("skills: not-a-list\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        load_skill_registry(path=invalid)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("budgets", "deadline_seconds", 0),
        ("budgets", "max_model_calls", 0),
        ("budgets", "max_tool_calls", 0),
    ],
)
def test_budgets_require_finite_positive_values(
    tmp_path: Path,
    section: str,
    field: str,
    value: int,
):
    document = _valid_document()
    document["skills"][0][section][field] = value

    with pytest.raises(ValidationError):
        _load(tmp_path, document)

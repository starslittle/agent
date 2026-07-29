import json
from hashlib import sha256
from pathlib import Path

from agent.prompts import (
    append_prompt_version,
    load_prompt,
    load_prompt_bytes,
    prompt_sha256,
    text_sha256,
)
from agent.prompts.loader import BACKEND_ROOT


ACTIVE_PROMPTS = {
    "agent/prompts/generate_default_system.txt",
    "agent/prompts/generate_fortune_system.txt",
    "agent/prompts/research_plan_structured.txt",
    "agent/prompts/research_grade_evidence.txt",
    "agent/prompts/research_synthesize_with_citations.txt",
    "agent/prompts/fortune_extract_birth_profile.txt",
}

PROMPT_BASELINE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "prompt_runtime_baseline.json"
)


def test_active_prompts_have_stable_backend_relative_paths_and_hashes():
    for relative_path in ACTIVE_PROMPTS:
        prompt_path = BACKEND_ROOT / relative_path
        assert prompt_path.is_file()
        raw_bytes = prompt_path.read_bytes()
        assert load_prompt_bytes(relative_path) == raw_bytes
        assert load_prompt(relative_path) == raw_bytes.decode("utf-8")
        digest = prompt_sha256(relative_path)
        assert digest == sha256(raw_bytes).hexdigest()
        assert len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)
        assert b"\r\n" not in raw_bytes


def test_public_stream_prompt_hashes_match_the_migration_baseline():
    baseline = json.loads(PROMPT_BASELINE_FIXTURE.read_text(encoding="utf-8"))

    assert baseline["schema_version"] == 2
    for relative_path, expected_hash in baseline["prompts"].items():
        assert relative_path in ACTIVE_PROMPTS
        assert prompt_sha256(relative_path) == expected_hash


def test_append_prompt_version_preserves_history_and_hashes_rendered_text():
    original = {
        "metadata": {
            "prompt_versions": [
                {
                    "stage": "router",
                    "path": "existing",
                    "sha256": "existing",
                }
            ]
        }
    }
    rendered = "已渲染的提示词"

    updated = append_prompt_version(
        original,
        stage="planner",
        relative_path="agent/prompts/research_plan_structured.txt",
        rendered_prompt=rendered,
        iteration=2,
    )

    assert len(original["metadata"]["prompt_versions"]) == 1
    versions = updated["metadata"]["prompt_versions"]
    assert len(versions) == 2
    assert versions[-1] == {
        "stage": "planner",
        "path": "agent/prompts/research_plan_structured.txt",
        "sha256": prompt_sha256(
            "agent/prompts/research_plan_structured.txt"
        ),
        "rendered_sha256": text_sha256(rendered),
        "rendered_characters": len(rendered),
        "content_capture_level": "hashed",
        "iteration": 2,
    }

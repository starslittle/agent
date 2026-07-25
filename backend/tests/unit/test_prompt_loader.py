from hashlib import sha256
from pathlib import Path

import yaml

from agent.prompts import (
    append_prompt_version,
    load_prompt,
    load_prompt_bytes,
    prompt_sha256,
    render_prompt,
    text_sha256,
)
from agent.prompts.loader import BACKEND_ROOT


ACTIVE_PROMPTS = {
    "agent/prompts/intent_classification.txt",
    "agent/prompts/generate_default_system.txt",
    "agent/prompts/generate_research_system.txt",
    "agent/prompts/generate_fortune_system.txt",
    "agent/prompts/direct_llm_system.txt",
    "agent/prompts/planner_research.txt",
    "agent/prompts/planner_fortune.txt",
    "agent/prompts/executor_tool_selection.txt",
    "agent/prompts/executor_birth_extract.txt",
    "agent/prompts/replanner.txt",
}


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


def test_prompt_renderer_only_replaces_explicit_placeholders():
    rendered = render_prompt(
        "agent/prompts/executor_birth_extract.txt",
        query="测试问题",
        current_task="提取出生信息",
    )

    assert "测试问题" in rendered
    assert "提取出生信息" in rendered
    assert '{"birth_date":' in rendered


def test_agent_config_prompt_paths_resolve_from_backend_root():
    config_path = Path(BACKEND_ROOT) / "configs" / "agents.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    configured_paths = {
        agent["config"]["prompt_template_path"]
        for agent in config["agents"]
        if agent.get("config", {}).get("prompt_template_path")
    }

    assert configured_paths <= ACTIVE_PROMPTS
    for relative_path in configured_paths:
        assert (BACKEND_ROOT / relative_path).is_file()


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
        relative_path="agent/prompts/planner_research.txt",
        rendered_prompt=rendered,
        iteration=2,
    )

    assert len(original["metadata"]["prompt_versions"]) == 1
    versions = updated["metadata"]["prompt_versions"]
    assert len(versions) == 2
    assert versions[-1] == {
        "stage": "planner",
        "path": "agent/prompts/planner_research.txt",
        "sha256": prompt_sha256("agent/prompts/planner_research.txt"),
        "rendered_sha256": text_sha256(rendered),
        "iteration": 2,
    }

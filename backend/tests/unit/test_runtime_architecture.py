from __future__ import annotations

import ast
from pathlib import Path

import yaml


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _python_files():
    for root in (BACKEND_ROOT / "agent", BACKEND_ROOT / "app"):
        yield from root.rglob("*.py")


def test_removed_execution_implementations_cannot_reappear():
    forbidden = [
        BACKEND_ROOT / "graph",
        BACKEND_ROOT / "app" / "runtime" / "service.py",
        BACKEND_ROOT / "app" / "api" / "agent_factory.py",
        BACKEND_ROOT / "app" / "api" / "intent_router.py",
        BACKEND_ROOT / "rag",
    ]
    assert all(
        not path.exists()
        or (path.is_dir() and not any(path.rglob("*.py")))
        for path in forbidden
    )

    forbidden_import_roots = {
        "graph",
        "langchain_community",
        "langchain_dashscope",
        "langchain_tavily",
    }
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.level == 0
            ):
                roots = {node.module.split(".", 1)[0]}
            else:
                continue
            assert not roots & forbidden_import_roots, path


def test_legacy_adapter_contains_protocol_mapping_not_agent_logic():
    source = (
        BACKEND_ROOT / "app" / "api" / "graph_routes.py"
    ).read_text(encoding="utf-8")
    assert "agent_runs.registry.start" in source
    assert "agent_runs.registry.events" in source
    assert "build_root_graph" not in source
    assert "ModelGateway" not in source
    assert "CapabilityExecutor" not in source


def test_agent_yaml_has_no_legacy_config_fields():
    document = yaml.safe_load(
        (BACKEND_ROOT / "configs" / "agents.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert all("config" not in agent for agent in document["agents"])

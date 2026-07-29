from __future__ import annotations

import json
import tomllib
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    BACKEND_ROOT / "tests" / "fixtures" / "runtime_dependency_baseline.json"
)


def test_single_runtime_dependency_snapshot_matches_pyproject_and_lock():
    baseline = json.loads(FIXTURE.read_text(encoding="utf-8"))
    project = tomllib.loads(
        (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    lock = tomllib.loads(
        (BACKEND_ROOT / "uv.lock").read_text(encoding="utf-8")
    )
    locked = {item["name"]: item["version"] for item in lock["package"]}
    direct = {
        item.split("[", 1)[0].split("==", 1)[0]: item.rsplit("==", 1)[-1]
        for item in project["project"]["dependencies"]
    }

    assert baseline["schema_version"] == 2
    for name, version in baseline["runtime"].items():
        if name == "python":
            assert project["project"]["requires-python"] == ">=3.11,<3.13"
            continue
        assert locked[name] == version
        assert direct[name] == version
    assert not (BACKEND_ROOT / "requirements.runtime.txt").exists()
    requirements_dir = BACKEND_ROOT / "requirements"
    assert not requirements_dir.exists() or not any(
        requirements_dir.rglob("*")
    )

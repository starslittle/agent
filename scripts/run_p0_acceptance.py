#!/usr/bin/env python3
"""Run the P0 Runtime acceptance layers and emit redacted JSON/Markdown reports."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "scripts" / "p0_runtime_matrix.json"
DEFAULT_OUTPUT = ROOT / "reports" / "p0-runtime-acceptance"
VALID_STATUSES = {"passed", "failed", "skipped", "not-run"}


def tool(name: str) -> str | None:
    return shutil.which(name)


def suite_definitions() -> list[dict[str, Any]]:
    uv = tool("uv")
    go = tool("go")
    npm = tool("npm")
    docker = tool("docker")
    git = tool("git")
    database_ready = bool(os.environ.get("TEST_DATABASE_URL"))
    return [
        {
            "id": "python_unit",
            "cwd": ROOT / "backend",
            "command": [uv, "run", "--frozen", "--group", "target-test", "pytest", "tests/unit", "-q"] if uv else None,
            "missing_reason": "uv is not installed",
        },
        {
            "id": "python_lint",
            "cwd": ROOT / "backend",
            "command": [uv, "run", "--frozen", "--extra", "dev", "ruff", "check", "agent", "app", "tests", "scripts"] if uv else None,
            "missing_reason": "uv is not installed",
        },
        {
            "id": "database_migrate",
            "cwd": ROOT / "go-backend",
            "command": [go, "run", "./cmd/migrate"] if go else None,
            "missing_reason": "go is not installed",
            "skip": not database_ready,
            "skip_reason": "TEST_DATABASE_URL is not configured for an isolated PostgreSQL database",
            "environment": {
                "GO_DATABASE_URL": os.environ.get("TEST_DATABASE_URL", ""),
            },
        },
        {
            "id": "python_postgres",
            "cwd": ROOT / "backend",
            "command": [uv, "run", "--frozen", "--group", "target-test", "pytest", "tests/integration/test_postgres_runtime_store.py", "-q"] if uv else None,
            "missing_reason": "uv is not installed",
            "skip": not database_ready,
            "skip_reason": "TEST_DATABASE_URL is not configured for an isolated PostgreSQL database",
        },
        {
            "id": "go_all",
            "cwd": ROOT / "go-backend",
            "command": [go, "test", "./..."] if go else None,
            "missing_reason": "go is not installed",
            # Database-backed integration tests run exactly once in the
            # dedicated go_postgres suite below.
            "environment": {"TEST_DATABASE_URL": ""},
        },
        {
            "id": "go_postgres",
            "cwd": ROOT / "go-backend",
            "command": [go, "test", "./internal/httpapi", "./internal/platform/postgres", "-run", "Integration", "-count=1"] if go else None,
            "missing_reason": "go is not installed",
            "skip": not database_ready,
            "skip_reason": "TEST_DATABASE_URL is not configured for an isolated PostgreSQL database",
        },
        {
            "id": "frontend_lint",
            "cwd": ROOT / "frontend",
            "command": [npm, "run", "lint"] if npm else None,
            "missing_reason": "npm is not installed",
        },
        {
            "id": "frontend_tests",
            "cwd": ROOT / "frontend",
            "command": [npm, "run", "test", "--", "--run"] if npm else None,
            "missing_reason": "npm is not installed",
        },
        {
            "id": "frontend_build",
            "cwd": ROOT / "frontend",
            "command": [npm, "run", "build"] if npm else None,
            "missing_reason": "npm is not installed",
        },
        {
            "id": "compose_config",
            "cwd": ROOT,
            "command": [docker, "compose", "-f", "docker-compose.yml", "config", "--quiet"] if docker else None,
            "missing_reason": "docker is not installed",
            "environment": {
                "POSTGRES_PASSWORD": "p0-config-placeholder",
                "PUBLIC_ORIGINS": "http://localhost:8080",
                "INTERNAL_AGENT_SECRET": "p0-config-placeholder-at-least-32-characters",
                "DASHSCOPE_API_KEY": "p0-config-placeholder",
            },
        },
        {
            "id": "diff_check",
            "cwd": ROOT,
            "command": [git, "diff", "--check"] if git else None,
            "missing_reason": "git is not installed",
        },
    ]


def run_suite(definition: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    result = {
        "id": definition["id"],
        "status": "not-run",
        "duration_ms": 0,
        "reason": None,
    }
    if definition.get("skip"):
        result.update(status="skipped", reason=definition["skip_reason"])
        return result
    command = definition.get("command")
    if not command or not command[0]:
        result["reason"] = definition["missing_reason"]
        return result

    print(f"\n==> {definition['id']}", flush=True)
    try:
        environment = os.environ.copy()
        environment.update(definition.get("environment", {}))
        completed = subprocess.run(
            command,
            cwd=definition["cwd"],
            check=False,
            timeout=1200,
            env=environment,
        )
        result["status"] = "passed" if completed.returncode == 0 else "failed"
        if completed.returncode != 0:
            result["reason"] = f"command exited with code {completed.returncode}"
    except subprocess.TimeoutExpired:
        result.update(status="failed", reason="command exceeded the 1200 second timeout")
    except OSError:
        result.update(status="not-run", reason="command could not be started")
    result["duration_ms"] = round((time.monotonic() - started) * 1000)
    return result


def derive_risks(matrix: dict[str, Any], suites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suite_status = {item["id"]: item["status"] for item in suites}
    risks = []
    precedence = ("failed", "not-run", "skipped")
    for risk in matrix["risks"]:
        statuses = [suite_status.get(suite_id, "not-run") for suite_id in risk["suites"]]
        status = "passed"
        for candidate in precedence:
            if candidate in statuses:
                status = candidate
                break
        risks.append({**risk, "status": status})
    return risks


def git_value(*args: str) -> str:
    git = tool("git")
    if not git:
        return "unavailable"
    completed = subprocess.run(
        [git, *args], cwd=ROOT, check=False, capture_output=True, text=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unavailable"


def write_reports(output_dir: Path, report: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# P0 Runtime Acceptance Summary",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- commit: `{report['commit']}`",
        f"- profile: `{report['profile']}`",
        f"- overall: **{report['overall_status']}**",
        "",
        "## Suites",
        "",
        "| Suite | Status | Duration | Reason |",
        "|---|---|---:|---|",
    ]
    for suite in report["suites"]:
        reason = suite["reason"] or "-"
        lines.append(
            f"| `{suite['id']}` | {suite['status']} | {suite['duration_ms']} ms | {reason} |"
        )
    lines.extend(["", "## Risks", "", "| Risk | Status | Evidence |", "|---|---|---|"])
    for risk in report["risks"]:
        evidence = "<br>".join(f"`{item}`" for item in risk["evidence"])
        lines.append(f"| {risk['title']} | {risk['status']} | {evidence} |")
    lines.extend([
        "",
        "> Reports contain only fixed test identifiers and status metadata; command output is not persisted.",
        "",
    ])
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("local", "full"), default="local")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    suites = [run_suite(definition) for definition in suite_definitions()]
    risks = derive_risks(matrix, suites)
    statuses = [item["status"] for item in suites] + [item["status"] for item in risks]
    if "failed" in statuses or "not-run" in statuses:
        overall = "failed"
    elif "skipped" in statuses or any(risk["status"] == "skipped" for risk in risks):
        overall = "partial"
    else:
        overall = "passed"
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": git_value("rev-parse", "HEAD"),
        "branch": git_value("branch", "--show-current"),
        "profile": args.profile,
        "overall_status": overall,
        "suites": suites,
        "risks": risks,
    }
    if any(item["status"] not in VALID_STATUSES for item in suites):
        raise RuntimeError("invalid suite status")
    write_reports(args.output_dir.resolve(), report)
    print(f"\nReport: {(args.output_dir / 'report.json').resolve()}")
    print(f"Summary: {(args.output_dir / 'summary.md').resolve()}")

    if overall == "failed":
        return 1
    if args.profile == "full" and overall != "passed":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

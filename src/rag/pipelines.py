from __future__ import annotations

"""
统一 RAG 出口：提供对外稳定接口
- query: 基于 agents.yaml 与 AgentExecutor 执行一次问答
- query_fortune: 命理双阶段检索（暂复用现有实现）
"""

from pathlib import Path
from typing import Optional

import yaml

from src.api.agent_factory import create_agent_from_config  # type: ignore


_AGENTS_CACHE: dict[str, object] = {}
_DEFAULT: Optional[str] = None


def _resolve_agents_yaml() -> Path:
    root = Path(__file__).resolve().parents[2]
    candidates = [
        root / "configs" / "agents.yaml",
        root / "backend" / "agents.yaml",
        root / "agents.yaml",
    ]
    for p in candidates:
        try:
            if p.exists():
                return p
        except Exception:
            continue
    tried = " | ".join(str(x) for x in candidates)
    raise FileNotFoundError(f"agents.yaml not found; tried: {tried}")


def _load_agents() -> None:
    global _AGENTS_CACHE, _DEFAULT
    if _AGENTS_CACHE:
        return
    yaml_path = _resolve_agents_yaml()
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    _AGENTS_CACHE = {}
    _DEFAULT = None
    for agent_cfg in data.get("agents", []):
        name = agent_cfg.get("name")
        conf = agent_cfg.get("config", {})
        if not name:
            continue
        _AGENTS_CACHE[name] = create_agent_from_config(conf)
        if agent_cfg.get("is_default"):
            _DEFAULT = name
    if _DEFAULT is None and _AGENTS_CACHE:
        _DEFAULT = list(_AGENTS_CACHE.keys())[0]


def query(question: str, *, agent_name: Optional[str] = None) -> str:
    _load_agents()
    name = agent_name or _DEFAULT
    if not name or name not in _AGENTS_CACHE:
        raise ValueError(f"unknown agent: {agent_name}")
    executor = _AGENTS_CACHE[name]
    result = executor.invoke({"input": question, "context": ""})
    text = str(result.get("output", "")) if isinstance(result, dict) else str(result)

    def _post_clean(s: str) -> str:
        lines = [ln.rstrip() for ln in (s or "").splitlines()]
        cleaned: list[str] = []
        for ln in lines:
            low = ln.lstrip().lower()
            if low.startswith("citations:") or low.startswith("notes:"):
                continue
            if low in ("missinginfo: none",):
                continue
            cleaned.append(ln)
        return "\n".join(cleaned).strip()

    return _post_clean(text)


def query_fortune(question: str, *, return_meta: bool = False):
    from src.rag.pipelines_fortune import query_fortune as _qf  # type: ignore
    return _qf(question, return_meta=return_meta)



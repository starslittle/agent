from __future__ import annotations

"""
最小可用的管道接口：当前内部仍调用现有 backend/agent_factory 与 agents.yaml
构造的执行器，以保持兼容。后续可逐步改为直接调用 src/rag 纯函数。
"""

from pathlib import Path
from typing import Optional

import yaml

from backend.agent_factory import create_agent_from_config


_AGENTS_CACHE: dict[str, object] = {}
_DEFAULT: Optional[str] = None


def _load_agents() -> None:
    global _AGENTS_CACHE, _DEFAULT
    if _AGENTS_CACHE:
        return
    yaml_path = Path(__file__).resolve().parents[2] / "backend" / "agents.yaml"
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
    """对外稳定接口：根据 agent_name 执行一次问答，返回纯文本答案。"""
    _load_agents()
    name = agent_name or _DEFAULT
    if not name or name not in _AGENTS_CACHE:
        raise ValueError(f"unknown agent: {agent_name}")
    executor = _AGENTS_CACHE[name]
    result = executor.invoke({"input": question})
    if isinstance(result, dict):
        return str(result.get("output", ""))
    return str(result)



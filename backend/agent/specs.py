from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent.prompts.loader import BACKEND_ROOT, load_prompt


WorkflowName = Literal["chat_v1", "research_v1", "fortune_v1"]

PROMPT_BUNDLES: dict[str, dict[str, str]] = {
    "chat_v1": {
        "generate": "agent/prompts/generate_default_system.txt",
    },
    "research_v1": {
        "plan": "agent/prompts/research_plan_structured.txt",
        "grade": "agent/prompts/research_grade_evidence.txt",
        "generate": "agent/prompts/research_synthesize_with_citations.txt",
    },
    "fortune_v1": {
        "extract": "agent/prompts/fortune_extract_birth_profile.txt",
        "generate": "agent/prompts/generate_fortune_system.txt",
    },
}


class AgentBudgets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deadline_seconds: int = Field(gt=0, le=900)
    max_model_calls: int = Field(gt=0, le=64)
    max_tool_calls: int = Field(ge=0, le=64)


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    is_default: bool = False
    workflow: WorkflowName
    model_profile: str
    prompt_bundle: str
    allowed_capabilities: list[str] = Field(default_factory=list)
    budgets: AgentBudgets

class AgentSpecFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: list[AgentSpec]
    aliases: dict[str, str] = Field(default_factory=dict)


class AgentCatalog:
    def __init__(
        self,
        document: AgentSpecFile,
        *,
        model_profiles: set[str],
        capabilities: set[str],
    ) -> None:
        self._agents = {item.name: item for item in document.agents}
        if len(self._agents) != len(document.agents):
            raise ValueError("agent names must be unique")
        defaults = [item.name for item in document.agents if item.is_default]
        if len(defaults) != 1:
            raise ValueError("exactly one default agent is required")
        self.default_agent = defaults[0]
        self._aliases = dict(document.aliases)
        self._document = document

        for alias, target in self._aliases.items():
            if alias in self._agents:
                raise ValueError(f"alias conflicts with agent name: {alias}")
            if target not in self._agents:
                raise ValueError(f"alias target does not exist: {target}")

        for spec in document.agents:
            if spec.model_profile not in model_profiles:
                raise ValueError(
                    f"agent {spec.name} references unknown model profile "
                    f"{spec.model_profile}"
                )
            if spec.prompt_bundle not in PROMPT_BUNDLES:
                raise ValueError(
                    f"agent {spec.name} references unknown prompt bundle "
                    f"{spec.prompt_bundle}"
                )
            for prompt_path in PROMPT_BUNDLES[spec.prompt_bundle].values():
                load_prompt(prompt_path)
            unknown = set(spec.allowed_capabilities) - capabilities
            if unknown:
                raise ValueError(
                    f"agent {spec.name} references unknown capabilities: "
                    f"{sorted(unknown)}"
                )
            if (
                spec.budgets.max_tool_calls == 0
                and spec.allowed_capabilities
            ):
                raise ValueError(
                    f"agent {spec.name} allows tools with zero tool budget"
                )

    def resolve(self, name: str | None) -> AgentSpec:
        key = (name or self.default_agent).strip()
        key = self._aliases.get(key, key)
        try:
            return self._agents[key]
        except KeyError as exc:
            raise LookupError(f"unknown agent: {name}") from exc

    def names(self) -> list[str]:
        return sorted(self._agents)

    def fingerprint(self) -> str:
        payload = json.dumps(
            self._document.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def prompt_for(bundle: str, stage: str) -> str:
    try:
        return PROMPT_BUNDLES[bundle][stage]
    except KeyError as exc:
        raise LookupError(f"unknown prompt bundle stage: {bundle}.{stage}") from exc


def load_agent_catalog(
    *,
    model_profiles: set[str],
    capabilities: set[str],
    path: Path | None = None,
) -> AgentCatalog:
    config_path = path or BACKEND_ROOT / "configs" / "agents.yaml"
    document = AgentSpecFile.model_validate(
        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    )
    return AgentCatalog(
        document,
        model_profiles=model_profiles,
        capabilities=capabilities,
    )


@lru_cache(maxsize=1)
def get_agent_catalog() -> AgentCatalog:
    from agent.capabilities import TARGET_CAPABILITY_SPECS
    from agent.models.factory import default_model_profiles

    return load_agent_catalog(
        model_profiles={item.name for item in default_model_profiles()},
        capabilities=set(TARGET_CAPABILITY_SPECS),
    )

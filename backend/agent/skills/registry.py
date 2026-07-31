from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import get_args

import yaml

from agent.prompts.loader import BACKEND_ROOT
from agent.specs import WorkflowName

from .types import SkillManifest, SkillManifestFile


class SkillRegistry:
    def __init__(
        self,
        document: SkillManifestFile,
        *,
        workflows: set[str],
        capabilities: set[str],
    ) -> None:
        self._document = document
        self._skills = {skill.id: skill for skill in document.skills}
        if len(self._skills) != len(document.skills):
            raise ValueError("skill ids must be unique")

        for skill in document.skills:
            if skill.workflow not in workflows:
                raise ValueError(
                    f"skill {skill.id} references unknown workflow {skill.workflow}"
                )
            unknown = set(skill.allowed_capabilities) - capabilities
            if unknown:
                raise ValueError(
                    f"skill {skill.id} references unknown capabilities: "
                    f"{sorted(unknown)}"
                )

    def resolve(self, skill_id: str) -> SkillManifest:
        key = skill_id.strip()
        try:
            return self._skills[key]
        except KeyError as exc:
            raise LookupError(f"unknown skill: {skill_id}") from exc

    def available(self) -> list[SkillManifest]:
        return sorted(
            (skill for skill in self._skills.values() if skill.available),
            key=lambda skill: skill.id,
        )

    def ids(self) -> list[str]:
        return sorted(self._skills)

    def fingerprint(self) -> str:
        payload = json.dumps(
            self._document.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_skill_registry(
    *,
    path: Path | None = None,
    workflows: set[str] | None = None,
    capabilities: set[str] | None = None,
) -> SkillRegistry:
    if capabilities is None:
        from agent.capabilities import TARGET_CAPABILITY_SPECS

        capabilities = set(TARGET_CAPABILITY_SPECS)
    document = SkillManifestFile.model_validate(
        yaml.safe_load(
            (path or BACKEND_ROOT / "configs" / "skills.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    return SkillRegistry(
        document,
        workflows=workflows or set(get_args(WorkflowName)),
        capabilities=capabilities,
    )


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    return load_skill_registry()

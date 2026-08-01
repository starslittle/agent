from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from agent.prompts.loader import BACKEND_ROOT

from .factory import default_model_profiles
from .types import ModelCapabilities, ModelProfile


class ModelCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    profile: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,127}$")
    available: bool = True


class ModelCatalogFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_model_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    models: list[ModelCatalogEntry] = Field(min_length=1, max_length=128)


class ResolvedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str
    profile: str
    provider: str
    model: str
    capabilities: ModelCapabilities
    temperature: float
    timeout_seconds: float
    max_retries: int
    fingerprint: str


class UnknownModelIDError(LookupError):
    code = "unknown_model_id"

    def __init__(self, model_id: str) -> None:
        super().__init__(f"unknown model_id: {model_id}")
        self.model_id = model_id


def _resolution_payload(model_id: str, profile: ModelProfile) -> dict:
    return {
        "model_id": model_id,
        "profile": profile.name,
        "provider": profile.provider,
        "model": profile.model,
        "capabilities": profile.capabilities.model_dump(mode="json"),
        "temperature": profile.temperature,
        "timeout_seconds": profile.timeout_seconds,
        "max_retries": profile.max_retries,
    }


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelCatalog:
    def __init__(
        self,
        document: ModelCatalogFile,
        *,
        profiles: list[ModelProfile],
        providers: set[str],
    ) -> None:
        self._document = document
        self._entries = {entry.id: entry for entry in document.models}
        if len(self._entries) != len(document.models):
            raise ValueError("model ids must be unique")
        self._profiles = {profile.name: profile for profile in profiles}
        if len(self._profiles) != len(profiles):
            raise ValueError("model profile names must be unique")

        for profile in profiles:
            if profile.provider not in providers:
                raise ValueError(
                    f"model profile {profile.name} references unknown provider "
                    f"{profile.provider}"
                )
        for entry in document.models:
            if entry.profile not in self._profiles:
                raise ValueError(
                    f"model {entry.id} references unknown profile {entry.profile}"
                )
        default = self._entries.get(document.default_model_id)
        if default is None:
            raise ValueError("default model_id must exist")
        if not default.available:
            raise ValueError("default model_id must be available")

    @property
    def default_model_id(self) -> str:
        return self._document.default_model_id

    def ids(self, *, available_only: bool = False) -> list[str]:
        return sorted(
            entry.id
            for entry in self._entries.values()
            if not available_only or entry.available
        )

    def resolve(self, model_id: str | None) -> ResolvedModel:
        key = (model_id or self.default_model_id).strip()
        try:
            entry = self._entries[key]
        except KeyError as exc:
            raise UnknownModelIDError(key) from exc
        if not entry.available:
            raise UnknownModelIDError(key)
        profile = self._profiles[entry.profile]
        payload = _resolution_payload(entry.id, profile)
        return ResolvedModel(**payload, fingerprint=_fingerprint(payload))

    def fingerprint(self) -> str:
        resolved = [
            _resolution_payload(model_id, self._profiles[self._entries[model_id].profile])
            for model_id in self.ids()
        ]
        return _fingerprint(
            {
                "config": self._document.model_dump(mode="json"),
                "resolved": resolved,
            }
        )


def load_model_catalog(
    *,
    path: Path | None = None,
    profiles: list[ModelProfile] | None = None,
    providers: set[str] | None = None,
) -> ModelCatalog:
    effective_profiles = profiles or default_model_profiles()
    effective_providers = providers or {
        profile.provider for profile in effective_profiles
    }
    document = ModelCatalogFile.model_validate(
        yaml.safe_load(
            (path or BACKEND_ROOT / "configs" / "models.yaml").read_text(
                encoding="utf-8"
            )
        )
    )
    return ModelCatalog(
        document,
        profiles=effective_profiles,
        providers=effective_providers,
    )


@lru_cache(maxsize=1)
def get_model_catalog() -> ModelCatalog:
    return load_model_catalog()

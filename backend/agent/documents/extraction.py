from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.models import ModelMessage, ModelRequest


DOCUMENT_EXTRACTION_AGENT = "document_extraction"
DOCUMENT_EXTRACTION_PURPOSE = "document_extraction"
EXTRACTION_VERSION = "document-extraction-v1"
PROMPT_VERSION = "document-extract-v1"
PROMPT_PATH = "agent/prompts/document_extract_v1.txt"
MODEL_PROFILE = "default_reasoning"


class DocumentExtractionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["qidian.document_extraction.v1"]
    run_purpose: Literal["document_extraction"]
    extraction_version: Literal["document-extraction-v1"]
    document_id: str = Field(min_length=1, max_length=128)
    document_revision_id: str = Field(min_length=1, max_length=128)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    markdown: str = Field(min_length=1, max_length=16_000)

    @model_validator(mode="after")
    def content_hash_matches(self) -> "DocumentExtractionEnvelope":
        actual = hashlib.sha256(self.markdown.encode("utf-8")).hexdigest()
        if actual != self.content_hash:
            raise ValueError("document content hash mismatch")
        return self


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_type: Literal[
        "confirmed_fact", "current_state", "personal_rule", "ai_analysis"
    ]
    domain: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    content: str = Field(min_length=1, max_length=450)
    source_location: str = Field(min_length=1, max_length=180)
    source_excerpt: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0, le=1)
    proposed_action: Literal["create", "update"]
    explanation: str = Field(min_length=1, max_length=400)

    @field_validator("content", "source_location", "source_excerpt", "explanation")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("text cannot be blank")
        return normalized

    @field_validator("domain")
    @classmethod
    def normalize_domain(cls, value: str) -> str:
        return value.strip().lower()


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[ExtractionCandidate] = Field(default_factory=list, max_length=30)


def parse_extraction_envelope(query: str) -> DocumentExtractionEnvelope | None:
    try:
        raw = json.loads(query)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or raw.get("kind") != "qidian.document_extraction.v1":
        return None
    return DocumentExtractionEnvelope.model_validate(raw)


class DocumentExtractor:
    def __init__(self, gateway) -> None:
        self._gateway = gateway
        prompt_file = Path(__file__).parents[1] / "prompts" / "document_extract_v1.txt"
        self._system_prompt = prompt_file.read_text(encoding="utf-8")
        self.prompt_hash = hashlib.sha256(
            self._system_prompt.encode("utf-8")
        ).hexdigest()

    def provenance(self) -> dict:
        profile = self._gateway.profile(MODEL_PROFILE)
        model_snapshot = {
            "model_id": "auto",
            "execution_profile": MODEL_PROFILE,
            "execution_provider": profile.provider,
            "execution_model": profile.model,
            "purpose": DOCUMENT_EXTRACTION_PURPOSE,
        }
        return {
            "workflow_name": "document_extraction_v1",
            "workflow_version": "1",
            "agent_name": DOCUMENT_EXTRACTION_AGENT,
            "agent_spec_hash": self.prompt_hash,
            "model_profile": MODEL_PROFILE,
            "model_provider": profile.provider,
            "model_name": profile.model,
            "prompt_bundle": PROMPT_VERSION,
            "prompt_bundle_hash": self.prompt_hash,
            "prompt_versions": {
                "document.extract": {
                    "path": PROMPT_PATH,
                    "sha256": self.prompt_hash,
                }
            },
            "capabilities": [],
            "model_id": "auto",
            "model_snapshot": model_snapshot,
            "requested_skill": None,
            "resolved_skills": [],
            "primary_skill": None,
            "selection_source": "direct",
            "skill_snapshot": None,
            "context_package_id": None,
            "route_confidence": 1.0,
            "route_requires_confirmation": False,
            "route_reason_code": DOCUMENT_EXTRACTION_PURPOSE,
            "suggested_skill": None,
            "route_prompt": None,
        }

    async def extract(self, envelope: DocumentExtractionEnvelope) -> ExtractionResult:
        # The Markdown is deliberately isolated in a user message. It is never
        # concatenated into the trusted system prompt and no tools are supplied.
        return await self._gateway.structured(
            MODEL_PROFILE,
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=self._system_prompt),
                    ModelMessage(
                        role="user",
                        content=(
                            "<untrusted_markdown>\n"
                            + envelope.markdown
                            + "\n</untrusted_markdown>"
                        ),
                    ),
                ],
                tools=[],
                max_tokens=4000,
            ),
            ExtractionResult,
        )

    async def event_data(self, envelope: DocumentExtractionEnvelope) -> dict:
        result = await self.extract(envelope)
        profile = self._gateway.profile(MODEL_PROFILE)
        candidates = [item.model_dump(mode="json") for item in result.candidates]
        return {
            "run_purpose": DOCUMENT_EXTRACTION_PURPOSE,
            "document_id": envelope.document_id,
            "document_revision_id": envelope.document_revision_id,
            "content_hash": envelope.content_hash,
            "extraction_version": EXTRACTION_VERSION,
            "prompt_version": PROMPT_VERSION,
            "prompt_hash": self.prompt_hash,
            "model_version": f"{profile.provider}/{profile.model}",
            "candidate_count": len(candidates),
            "low_confidence_count": sum(
                1 for item in result.candidates if item.confidence < 0.65
            ),
            "candidates": candidates,
        }

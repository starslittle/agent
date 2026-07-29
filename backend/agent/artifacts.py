from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    citation_id: str
    title: str
    url: HttpUrl
    snippet: str = ""
    source_type: Literal["web", "knowledge", "tool"]


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_type: str
    schema_version: int = Field(default=1, ge=1)
    content_hash: str
    media_type: str
    size_bytes: int = Field(ge=0)


class InlineArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: ArtifactRef
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def create_citation(
    *,
    title: str,
    url: str,
    snippet: str = "",
    source_type: Literal["web", "knowledge", "tool"] = "web",
) -> Citation:
    citation_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return Citation(
        citation_id=citation_id,
        title=title or url,
        url=url,
        snippet=snippet,
        source_type=source_type,
    )


def create_inline_artifact(
    *,
    artifact_type: str,
    content: str,
    media_type: str = "text/plain; charset=utf-8",
    metadata: dict[str, Any] | None = None,
) -> InlineArtifact:
    encoded = content.encode("utf-8")
    content_hash = hashlib.sha256(encoded).hexdigest()
    artifact_id = f"{artifact_type}:{content_hash[:24]}"
    return InlineArtifact(
        ref=ArtifactRef(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content_hash=content_hash,
            media_type=media_type,
            size_bytes=len(encoded),
        ),
        content=content,
        metadata=metadata or {},
    )


def create_json_artifact(
    *,
    artifact_type: str,
    value: Any,
    metadata: dict[str, Any] | None = None,
) -> InlineArtifact:
    content = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return create_inline_artifact(
        artifact_type=artifact_type,
        content=content,
        media_type="application/json",
        metadata=metadata,
    )

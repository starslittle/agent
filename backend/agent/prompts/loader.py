"""Load versioned prompts from paths relative to the backend directory."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _resolve_prompt_path(relative_path: str) -> Path:
    candidate = (BACKEND_ROOT / relative_path).resolve()
    if candidate != BACKEND_ROOT and BACKEND_ROOT not in candidate.parents:
        raise ValueError(f"Prompt path escapes backend root: {relative_path}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Prompt file not found: {candidate}")
    return candidate


@lru_cache(maxsize=64)
def load_prompt_bytes(relative_path: str) -> bytes:
    """Return the exact bytes used for cross-language prompt verification."""
    return _resolve_prompt_path(relative_path).read_bytes()


@lru_cache(maxsize=64)
def load_prompt(relative_path: str) -> str:
    """Decode the exact UTF-8 file content without whitespace normalization."""
    return load_prompt_bytes(relative_path).decode("utf-8")


def prompt_sha256(relative_path: str) -> str:
    """Hash the exact UTF-8 file bytes; Go must hash os.ReadFile output."""
    return sha256(load_prompt_bytes(relative_path)).hexdigest()


def text_sha256(text: str) -> str:
    """Hash rendered prompt text without storing potentially sensitive content."""
    return sha256(text.encode("utf-8")).hexdigest()


def prompt_version_entry(
    *,
    stage: str,
    relative_path: str,
    rendered_prompt: str | None = None,
    iteration: int | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "stage": stage,
        "path": relative_path,
        "sha256": prompt_sha256(relative_path),
    }
    if rendered_prompt is not None:
        entry["rendered_sha256"] = text_sha256(rendered_prompt)
        entry["rendered_characters"] = len(rendered_prompt)
        entry["content_capture_level"] = "hashed"
    if iteration is not None:
        entry["iteration"] = iteration
    return entry


def append_prompt_version(
    state: dict[str, Any],
    *,
    stage: str,
    relative_path: str,
    rendered_prompt: str | None = None,
    iteration: int | None = None,
) -> dict[str, Any]:
    """Return a copied state with one actual prompt invocation appended."""
    metadata = dict(state.get("metadata") or {})
    versions = list(metadata.get("prompt_versions") or [])
    versions.append(
        prompt_version_entry(
            stage=stage,
            relative_path=relative_path,
            rendered_prompt=rendered_prompt,
            iteration=iteration,
        )
    )
    metadata["prompt_versions"] = versions
    return {**state, "metadata": metadata}


def render_prompt(relative_path: str, **values: object) -> str:
    """Render explicit ``{{name}}`` placeholders without interpreting JSON braces."""
    rendered = load_prompt(relative_path)
    for name, value in values.items():
        rendered = rendered.replace("{{" + name + "}}", str(value))
    return rendered

from __future__ import annotations

from typing import cast

from agent.capabilities import (
    CapabilityExecutor,
    TARGET_CAPABILITY_SPECS,
)
from agent.tools.registry import get_tool_registry
from agent.graph import build_root_graph
from agent.models import ModelGateway, default_model_profiles, get_model_catalog
from agent.specs import get_agent_catalog


def validate_target_runtime() -> dict:
    """Validate target references and compile the graph without provider I/O."""
    catalog = get_agent_catalog()
    model_catalog = get_model_catalog()
    profiles = {item.name: item for item in default_model_profiles()}
    required_model_capabilities = {
        "chat_v1": ("streaming",),
        "research_v1": ("streaming", "json_mode"),
        "fortune_v1": ("streaming", "json_mode"),
    }
    for agent_name in catalog.names():
        spec = catalog.resolve(agent_name)
        profile = profiles[spec.model_profile]
        for capability_name in required_model_capabilities[spec.workflow]:
            if not getattr(profile.capabilities, capability_name):
                raise ValueError(
                    f"agent {agent_name} requires model capability "
                    f"{capability_name}"
                )
        missing = set(spec.allowed_capabilities) - set(
            TARGET_CAPABILITY_SPECS
        )
        if missing:
            raise ValueError(
                f"agent {agent_name} has capabilities without target schemas: "
                f"{sorted(missing)}"
            )
        for capability_name in spec.allowed_capabilities:
            capability = TARGET_CAPABILITY_SPECS[capability_name]
            definition = get_tool_registry().get(capability_name)
            if (
                capability.effect != definition.effect
                or capability.idempotent != definition.idempotent
                or capability.shadow_allowed != definition.shadow_allowed
            ):
                raise ValueError(
                    f"capability policy mismatch: {capability_name}"
                )
            if not capability.idempotent:
                raise ValueError(
                    "non-idempotent capabilities require a durable "
                    f"operation ledger before activation: {capability_name}"
                )

    graph = build_root_graph(
        cast(ModelGateway, object()),
        cast(CapabilityExecutor, object()),
        catalog,
    )
    if graph is None:
        raise RuntimeError("target graph compilation failed")
    return {
        "agents": catalog.names(),
        "workflows": ["chat_v1", "research_v1", "fortune_v1"],
        "model_profiles": sorted(profiles),
        "model_ids": model_catalog.ids(available_only=True),
        "model_catalog_fingerprint": model_catalog.fingerprint(),
        "capabilities": sorted(TARGET_CAPABILITY_SPECS),
        "graph": "qidian_root_v1",
    }

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .registry import SkillRegistry


class PublicCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=500)


class PublicContextScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=128)


class PublicSkill(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    version: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=1_000)
    command: str = Field(pattern=r"^/[a-z][a-z0-9_-]{0,63}$")
    public_purpose: str = Field(min_length=1, max_length=1_000)
    public_capabilities: list[PublicCapability] = Field(max_length=64)
    context_scope: list[PublicContextScope] = Field(max_length=8)
    confirmation_summary: str = Field(min_length=1, max_length=1_000)
    may_propose_updates: bool
    available: bool
    effective: bool


_CAPABILITY_COPY = {
    "tavily_search": PublicCapability(
        label="联网检索",
        description="查找公开网页信息，并保留可追溯来源。",
    ),
    "get_current_date": PublicCapability(
        label="当前日期",
        description="读取当前日期，校准排盘所需的时间背景。",
    ),
    "get_lunar_chart": PublicCapability(
        label="历法排盘",
        description="根据明确输入计算农历与四柱等确定性结果。",
    ),
    "get_ziwei_chart": PublicCapability(
        label="紫微排盘",
        description="根据明确输入生成确定性的紫微斗数盘面。",
    ),
}

_CONTEXT_COPY = {
    "confirmed_fact": PublicContextScope(label="你确认的事实"),
    "current_state": PublicContextScope(label="你的当前状态"),
    "personal_rule": PublicContextScope(label="你确认的个人规则"),
    "ai_analysis": PublicContextScope(label="你主动保留的 AI 分析"),
}


def public_skill_catalog(
    registry: SkillRegistry,
    *,
    effective_skill_ids: set[str] | None = None,
) -> list[PublicSkill]:
    """Create a fail-closed, field-whitelisted browser-safe projection."""

    projected: list[PublicSkill] = []
    for skill in registry.available():
        if not skill.available or not skill.ui.visible:
            continue
        try:
            capabilities = [_CAPABILITY_COPY[item] for item in skill.allowed_capabilities]
            context_scope = [_CONTEXT_COPY[item] for item in skill.public.context_scope]
        except KeyError:
            # A new internal capability or context class is hidden until public copy
            # is reviewed and explicitly added to this allowlist.
            continue
        effective = effective_skill_ids is None or skill.id in effective_skill_ids
        projected.append(
            PublicSkill(
                id=skill.id,
                version=skill.version,
                title=skill.title,
                description=skill.description,
                command=skill.ui.command,
                public_purpose=skill.public.purpose,
                public_capabilities=capabilities,
                context_scope=context_scope,
                confirmation_summary=skill.public.confirmation_summary,
                may_propose_updates=skill.memory.may_propose_updates,
                available=True,
                effective=effective,
            )
        )
    return sorted(projected, key=lambda item: item.id)

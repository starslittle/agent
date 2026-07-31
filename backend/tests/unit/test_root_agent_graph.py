from __future__ import annotations

import asyncio

import pytest

from agent.artifacts import create_inline_artifact
from agent.capabilities import (
    CapabilityResult,
    SearchCapabilityOutput,
    SearchResultItem,
    TextCapabilityOutput,
)
from agent.application import (
    LangGraphAgentApplication,
    RunCommand,
    RuntimeEvent,
)
from agent.models import (
    ModelStreamEvent,
    ModelStreamEventType,
    ModelUsage,
)
from agent.workflows.fortune_v1 import BirthProfile
from agent.workflows.research_v1 import EvidenceGrade, ResearchPlan
from agent.specs import get_agent_catalog
from app.runtime.langgraph_v1 import LangGraphV1Runtime
from app.runtime.models import AgentRunRequest, ChatMessage


class FakeGateway:
    def __init__(
        self,
        *,
        birth_profile: BirthProfile | None = None,
        research_plan: ResearchPlan | None = None,
        evidence_grades: list[EvidenceGrade] | None = None,
    ):
        self.birth_profile = birth_profile
        self.research_plan = research_plan or ResearchPlan(
            questions=["现状是什么？", "主要风险是什么？"],
            search_queries=["启点 现状", "启点 风险"],
        )
        self.evidence_grades = list(evidence_grades or [])
        self.calls: list[tuple[str, str]] = []

    async def structured(self, profile_name, request, output_type):
        self.calls.append(("structured", output_type.__name__))
        if output_type is ResearchPlan:
            return self.research_plan
        if output_type is EvidenceGrade:
            if self.evidence_grades:
                return self.evidence_grades.pop(0)
            return EvidenceGrade(
                sufficient=True,
                covered_question_indexes=list(
                    range(len(self.research_plan.questions))
                ),
                gaps=[],
                supplemental_search_queries=[],
                assessment="证据已覆盖全部研究问题。",
            )
        if output_type is BirthProfile:
            return self.birth_profile or BirthProfile()
        raise AssertionError(output_type)

    async def stream(self, profile_name, request):
        self.calls.append(("stream", profile_name))
        yield ModelStreamEvent(
            type=ModelStreamEventType.DELTA,
            text="第一段",
            model="fake-model",
        )
        yield ModelStreamEvent(
            type=ModelStreamEventType.DELTA,
            text="第二段",
            model="fake-model",
        )
        usage = ModelUsage(
            input_tokens=10,
            output_tokens=4,
            total_tokens=14,
        )
        yield ModelStreamEvent(
            type=ModelStreamEventType.USAGE,
            model="fake-model",
            usage=usage,
        )
        yield ModelStreamEvent(
            type=ModelStreamEventType.COMPLETED,
            model="fake-model",
            finish_reason="stop",
            usage=usage,
        )


class FakeCapabilities:
    def __init__(self):
        self.calls: list[tuple[str, dict, str, bool]] = []

    async def execute(
        self,
        name,
        arguments,
        *,
        context,
        allowed_capabilities,
        stage,
        event_sink=None,
        event_metadata=None,
    ):
        self.calls.append(
            (name, arguments, context.execution_id, context.shadow)
        )
        if event_sink:
            event_sink(
                "tool.started",
                {"name": name, "stage": stage, **(event_metadata or {})},
            )
            event_sink(
                "tool.completed",
                {"name": name, "stage": stage, **(event_metadata or {})},
            )
        output = (
            SearchCapabilityOutput(
                items=[
                    SearchResultItem(
                        title=f"来源 {arguments['query']}",
                        url=(
                            "https://example.invalid/"
                            + str(len(self.calls))
                        ),
                        snippet="可验证的检索摘要",
                    )
                ]
            )
            if name == "tavily_search"
            else TextCapabilityOutput(
                content=f"evidence for {arguments}"
            )
        )
        return CapabilityResult(
            name=name,
            output=output,
            duration_ms=1,
            idempotency_key=f"fake-{name}",
        )


async def collect_events(
    *,
    requested_workflow: str,
    gateway: FakeGateway,
    capabilities: FakeCapabilities,
    cancel_event: asyncio.Event | None = None,
):
    application = LangGraphAgentApplication(
        gateway=gateway,
        capability_executor=capabilities,
    )
    return [
        event
        async for event in application.stream(
            RunCommand(
                execution_id="exec-test",
                query="测试问题",
                messages=[{"role": "user", "content": "历史问题"}],
                requested_workflow=requested_workflow,
                shadow=False,
                cancel_event=cancel_event,
            )
        )
    ]


def test_workflow_aliases_are_explicit_and_unknown_values_fail_closed():
    catalog = get_agent_catalog()
    assert catalog.resolve("default_llm_agent").workflow == "chat_v1"
    assert catalog.resolve("general_rag_agent").workflow == "research_v1"
    assert catalog.resolve("fortune").workflow == "fortune_v1"
    with pytest.raises(LookupError, match="unknown agent"):
        catalog.resolve("invented_agent")


@pytest.mark.asyncio
async def test_chat_uses_root_graph_stream_and_never_calls_capability():
    gateway = FakeGateway()
    capabilities = FakeCapabilities()

    events = await collect_events(
        requested_workflow="default_llm_agent",
        gateway=gateway,
        capabilities=capabilities,
    )

    assert [event.type for event in events] == [
        "route.selected",
        "prompt.used",
        "model.started",
        "answer.delta",
        "answer.delta",
        "usage",
        "model.completed",
        "workflow.completed",
    ]
    assert "".join(
        event.data["text"]
        for event in events
        if event.type == "answer.delta"
    ) == "第一段第二段"
    assert capabilities.calls == []


@pytest.mark.asyncio
async def test_research_uses_structured_plan_and_bounded_search_fanout():
    gateway = FakeGateway()
    capabilities = FakeCapabilities()

    events = await collect_events(
        requested_workflow="research_agent",
        gateway=gateway,
        capabilities=capabilities,
    )

    assert gateway.calls[0] == ("structured", "ResearchPlan")
    assert [call[0] for call in capabilities.calls] == [
        "tavily_search",
        "tavily_search",
    ]
    assert all(call[2] == "exec-test" for call in capabilities.calls)
    assert any(event.type == "workflow.completed" for event in events)
    assert sum(event.type == "tool.completed" for event in events) == 2
    artifact_event = next(
        event for event in events if event.type == "artifact.created"
    )
    assert artifact_event.data["artifact_type"] == "research_evidence"
    assert artifact_event.data["citation_count"] == 2
    citation_events = [
        event for event in events if event.type == "citation.created"
    ]
    assert [event.data["sequence"] for event in citation_events] == [1, 2]
    assert all(
        event.data["artifact_id"] == artifact_event.data["artifact_id"]
        for event in citation_events
    )
    assert all(
        {
            "citation_id",
            "title",
            "url",
            "snippet",
            "source_type",
            "artifact_id",
            "sequence",
        }
        <= event.data.keys()
        for event in citation_events
    )
    grade = next(
        event
        for event in events
        if event.type == "progress"
        and event.data.get("stage") == "research.grade"
    )
    assert grade.data["sufficient"] is True
    assert grade.data["will_supplement"] is False


@pytest.mark.asyncio
async def test_research_supplemental_retrieval_stops_at_tool_budget():
    gateway = FakeGateway(
        evidence_grades=[
            EvidenceGrade(
                sufficient=False,
                covered_question_indexes=[0],
                gaps=["缺少风险维度证据"],
                supplemental_search_queries=[
                    "启点 风险案例",
                    "启点 风险数据",
                    "启点 风险应对",
                    "不会执行的第四条",
                ],
                assessment="需要补充检索。",
            ),
            EvidenceGrade(
                sufficient=False,
                covered_question_indexes=[0, 1],
                gaps=["来源仍有冲突"],
                supplemental_search_queries=["预算外检索词"],
                assessment="证据仍有冲突。",
            ),
        ]
    )
    capabilities = FakeCapabilities()

    events = await collect_events(
        requested_workflow="research_agent",
        gateway=gateway,
        capabilities=capabilities,
    )

    assert [call[1]["query"] for call in capabilities.calls] == [
        "启点 现状",
        "启点 风险",
        "启点 风险案例",
        "启点 风险数据",
        "启点 风险应对",
    ]
    grades = [
        event
        for event in events
        if event.type == "progress"
        and event.data.get("stage") == "research.grade"
    ]
    assert len(grades) == 2
    assert grades[0].data["will_supplement"] is True
    assert grades[1].data["will_supplement"] is False
    assert grades[1].data["exhausted_reason"] == "tool_budget_exhausted"
    artifacts = [
        event for event in events if event.type == "artifact.created"
    ]
    assert len(artifacts) == 1
    assert artifacts[0].data["citation_count"] == 5
    assert any(event.type == "workflow.completed" for event in events)


@pytest.mark.asyncio
async def test_fortune_missing_birth_fields_returns_clarification_without_chart():
    gateway = FakeGateway(
        birth_profile=BirthProfile(
            domain="bazi",
            personal_analysis=True,
            birth_date="1990-01-01",
        )
    )
    capabilities = FakeCapabilities()

    events = await collect_events(
        requested_workflow="fortune_agent",
        gateway=gateway,
        capabilities=capabilities,
    )

    answer = "".join(
        event.data["text"]
        for event in events
        if event.type == "answer.delta"
    )
    assert "出生时间" in answer
    assert "性别" in answer
    assert "出生城市" in answer
    assert capabilities.calls == []
    assert ("stream", "default_reasoning") not in gateway.calls


@pytest.mark.asyncio
async def test_complete_ziwei_profile_uses_deterministic_chart_then_interprets():
    gateway = FakeGateway(
        birth_profile=BirthProfile(
            domain="ziwei",
            personal_analysis=True,
            birth_date="1990-01-01",
            birth_time="08:30",
            gender="女",
            birthplace="杭州",
        )
    )
    capabilities = FakeCapabilities()

    events = await collect_events(
        requested_workflow="fortune_agent",
        gateway=gateway,
        capabilities=capabilities,
    )

    assert capabilities.calls[0][0] == "get_ziwei_chart"
    assert capabilities.calls[0][1]["birthplace"] == "杭州"
    assert ("stream", "default_reasoning") in gateway.calls
    assert any(event.type == "workflow.completed" for event in events)
    assert any(
        event.type == "artifact.created"
        and event.data["artifact_type"] == "fortune_chart"
        for event in events
    )


@pytest.mark.asyncio
async def test_research_partial_search_failure_keeps_valid_citations():
    class PartiallyFailingCapabilities(FakeCapabilities):
        async def execute(self, name, arguments, **kwargs):
            if "风险" in arguments["query"]:
                sink = kwargs.get("event_sink")
                metadata = kwargs.get("event_metadata") or {}
                if sink:
                    sink(
                        "tool.started",
                        {
                            "name": name,
                            "stage": kwargs["stage"],
                            **metadata,
                        },
                    )
                    sink(
                        "tool.failed",
                        {
                            "name": name,
                            "stage": kwargs["stage"],
                            "error_code": "FakeSearchError",
                            **metadata,
                        },
                    )
                raise RuntimeError("search failed")
            return await super().execute(name, arguments, **kwargs)

    events = await collect_events(
        requested_workflow="research_agent",
        gateway=FakeGateway(),
        capabilities=PartiallyFailingCapabilities(),
    )

    progress = [
        event
        for event in events
        if event.type == "progress"
        and event.data.get("stage") == "research.collect"
    ][-1]
    artifact = next(
        event for event in events if event.type == "artifact.created"
    )
    assert progress.data["succeeded"] == 1
    assert progress.data["failed"] == 1
    assert progress.data["degraded"] is True
    assert artifact.data["citation_count"] == 1
    assert sum(event.type == "citation.created" for event in events) == 1
    assert any(event.type == "workflow.completed" for event in events)


@pytest.mark.asyncio
async def test_research_all_search_failures_degrade_without_failing_run():
    class FailingCapabilities(FakeCapabilities):
        async def execute(self, name, arguments, **kwargs):
            sink = kwargs.get("event_sink")
            metadata = kwargs.get("event_metadata") or {}
            if sink:
                sink(
                    "tool.started",
                    {
                        "name": name,
                        "stage": kwargs["stage"],
                        **metadata,
                    },
                )
                sink(
                    "tool.failed",
                    {
                        "name": name,
                        "stage": kwargs["stage"],
                        "error_code": "FakeSearchError",
                        **metadata,
                    },
                )
            raise RuntimeError("search failed")

    events = await collect_events(
        requested_workflow="research_agent",
        gateway=FakeGateway(),
        capabilities=FailingCapabilities(),
    )

    progress = [
        event
        for event in events
        if event.type == "progress"
        and event.data.get("stage") == "research.collect"
    ][-1]
    artifact = next(
        event for event in events if event.type == "artifact.created"
    )
    assert progress.data["succeeded"] == 0
    assert progress.data["failed"] == 2
    assert artifact.data["citation_count"] == 0
    assert any(event.type == "answer.delta" for event in events)
    assert any(event.type == "workflow.completed" for event in events)


@pytest.mark.asyncio
async def test_research_cancellation_is_not_converted_to_degraded_evidence():
    class CancelledCapabilities(FakeCapabilities):
        async def execute(self, name, arguments, **kwargs):
            kwargs["context"].cancel_event.set()
            raise asyncio.CancelledError

    cancel_event = asyncio.Event()
    with pytest.raises(asyncio.CancelledError):
        await collect_events(
            requested_workflow="research_agent",
            gateway=FakeGateway(),
            capabilities=CancelledCapabilities(),
            cancel_event=cancel_event,
        )


@pytest.mark.asyncio
async def test_research_deduplicates_citations_across_queries():
    class DuplicateSourceCapabilities(FakeCapabilities):
        async def execute(
            self,
            name,
            arguments,
            *,
            context,
            allowed_capabilities,
            stage,
            event_sink=None,
            event_metadata=None,
        ):
            output = SearchCapabilityOutput(
                items=[
                    SearchResultItem(
                        title="同一来源",
                        url="https://example.invalid/shared",
                        snippet="同一份可验证摘要",
                    )
                ]
            )
            return CapabilityResult(
                name=name,
                output=output,
                duration_ms=1,
                idempotency_key=f"fake-{arguments['query']}",
            )

    events = await collect_events(
        requested_workflow="research_agent",
        gateway=FakeGateway(),
        capabilities=DuplicateSourceCapabilities(),
    )

    artifact = next(
        event for event in events if event.type == "artifact.created"
    )
    grade = next(
        event
        for event in events
        if event.type == "progress"
        and event.data.get("stage") == "research.grade"
    )
    assert artifact.data["citation_count"] == 1
    assert grade.data["unique_sources"] == 1
    assert grade.data["sufficient"] is False
    citations = [event for event in events if event.type == "citation.created"]
    assert len(citations) == 1
    assert citations[0].data["sequence"] == 1


def test_inline_artifact_ids_are_content_addressed_and_stable():
    first = create_inline_artifact(
        artifact_type="fortune_chart",
        content="同一份排盘",
    )
    second = create_inline_artifact(
        artifact_type="fortune_chart",
        content="同一份排盘",
    )

    assert first.ref == second.ref
    assert first.ref.artifact_id.startswith("fortune_chart:")
    assert first.ref.size_bytes == len("同一份排盘".encode("utf-8"))


@pytest.mark.asyncio
async def test_v1_runtime_adapter_maps_request_and_events_to_target_application():
    class FakeApplication:
        def __init__(self):
            self.command = None

        async def stream(self, command):
            self.command = command
            yield RuntimeEvent(type="answer.delta", data={"text": "ok"})

    application = FakeApplication()
    runtime = LangGraphV1Runtime(application=application)
    request = AgentRunRequest(
        execution_id="exec-adapter",
        run_id="run-adapter",
        request_id="request-adapter",
        idempotency_key="idem-adapter",
        conversation_id="conversation-adapter",
        agent_name="fortune_agent",
        query="我的问题",
        messages=[ChatMessage(role="assistant", content="历史回答")],
    )

    events = [
        event
        async for event in runtime.stream(request, asyncio.Event())
    ]

    assert events == [("answer.delta", {"text": "ok"})]
    assert application.command.requested_workflow == "fortune_agent"
    assert application.command.messages == [
        {"role": "assistant", "content": "历史回答"}
    ]

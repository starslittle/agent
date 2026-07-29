from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.api import agent_runs, graph_routes
from app.runtime.registry import ExecutionRegistry
from app.runtime.models import RunStatus


async def _response_events(request):
    response = await graph_routes.query_stream_graph(request)
    return [event async for event in response.body_iterator]


def test_legacy_stream_is_a_thin_mapper_over_the_shared_registry(monkeypatch):
    captured = {}

    class FakeRuntime:
        graph_version = "qidian-root-v1"

        async def stream(self, request, cancel_event):
            captured["request"] = request
            yield "route.selected", {"selected_workflow": "research_v1"}
            yield "progress", {
                "stage": "research.collect",
                "message": "检索证据",
            }
            yield "answer.delta", {"text": "你"}
            yield "progress", {
                "stage": "research.synthesize",
                "message": "总结",
            }
            yield "answer.delta", {"text": "好"}

        async def cancel(self, execution_id):
            return None

    monkeypatch.setattr(
        agent_runs,
        "registry",
        ExecutionRegistry(FakeRuntime(), service_version="test"),
    )
    request = SimpleNamespace(
        query="研究问题",
        agent_name="research_agent",
        chat_history=[
            {"role": "user", "content": "前文"},
            {"role": "assistant", "content": "回答"},
        ],
    )

    events = asyncio.run(_response_events(request))
    payloads = [json.loads(event["data"]) for event in events]
    run_request = captured["request"]

    assert run_request.agent_name == "research_agent"
    assert [item.model_dump() for item in run_request.messages] == [
        {"role": "user", "content": "前文"},
        {"role": "assistant", "content": "回答"},
    ]
    assert run_request.metadata == {"transport": "legacy_sse"}
    assert payloads == [
        {
            "type": "delta",
            "data": "Step1: 检索证据\n",
            "isThinking": True,
            "thinkingFinished": False,
        },
        {
            "type": "delta",
            "data": "你",
            "isThinking": False,
            "thinkingFinished": True,
        },
        {
            "type": "delta",
            "data": "Step2: 总结\n",
            "isThinking": True,
            "thinkingFinished": False,
        },
        {
            "type": "delta",
            "data": "好",
            "isThinking": False,
            "thinkingFinished": False,
        },
        {"type": "done"},
    ]


def test_legacy_transport_disconnect_does_not_mean_semantic_cancel(
    monkeypatch,
):
    class DetachedRuntime:
        def __init__(self):
            self.release = asyncio.Event()

        async def stream(self, request, cancel_event):
            yield "answer.delta", {"text": "first"}
            await self.release.wait()
            yield "answer.delta", {"text": "second"}

        async def cancel(self, execution_id):
            raise AssertionError("transport detach must not call cancel")

    runtime = DetachedRuntime()
    registry = ExecutionRegistry(runtime, service_version="test")
    monkeypatch.setattr(agent_runs, "registry", registry)
    request = SimpleNamespace(
        query="普通问题",
        agent_name="default_llm_agent",
        chat_history=[],
    )

    async def scenario():
        response = await graph_routes.query_stream_graph(request)
        iterator = response.body_iterator
        first = await anext(iterator)
        await iterator.aclose()
        execution_id = next(iter(registry._executions))
        snapshot = await registry.snapshot(execution_id)
        assert json.loads(first["data"])["data"] == "first"
        assert snapshot.status == RunStatus.RUNNING
        runtime.release.set()
        for _ in range(100):
            snapshot = await registry.snapshot(execution_id)
            if snapshot.status.terminal:
                break
            await asyncio.sleep(0.01)
        assert snapshot.status == RunStatus.COMPLETED

    asyncio.run(scenario())

from types import SimpleNamespace

import pytest

from agent.prompts import prompt_sha256
from app.api.intent_router import INTENT_CLASSIFICATION_PROMPT, IntentRouter
from graph.nodes import executor as executor_module
from graph.nodes import router as router_module


class _FakeClassificationChain:
    def invoke(self, _payload):
        return "chat"


def _intent_router_without_provider() -> IntentRouter:
    router = IntentRouter.__new__(IntentRouter)
    router.classification_chain = _FakeClassificationChain()
    router.chat_keywords = {
        "你好",
        "hi",
        "hello",
        "介绍",
        "功能",
        "能做什么",
    }
    return router


def test_intent_prompt_is_only_recorded_when_llm_classifier_runs():
    router = _intent_router_without_provider()

    shortcut_intent, shortcut_trace = router.classify_intent_with_trace("你好")
    llm_input = "请说说你对此事可能持有什么样的普通看法以及理由吧"
    llm_intent, llm_trace = router.classify_intent_with_trace(llm_input)

    assert shortcut_intent == "chat"
    assert shortcut_trace is None
    assert llm_intent == "chat"
    assert llm_trace is not None
    assert llm_trace["stage"] == "intent_classification"
    assert llm_trace["path"] == "agent/prompts/intent_classification.txt"
    assert llm_trace["sha256"] == prompt_sha256(
        "agent/prompts/intent_classification.txt"
    )
    assert llm_trace["rendered_sha256"]
    assert llm_input in INTENT_CLASSIFICATION_PROMPT.replace(
        "{user_input}", llm_input
    )


@pytest.mark.asyncio
async def test_router_moves_intent_prompt_trace_into_state_metadata(monkeypatch):
    prompt_version = {
        "stage": "intent_classification",
        "path": "agent/prompts/intent_classification.txt",
        "sha256": prompt_sha256("agent/prompts/intent_classification.txt"),
    }

    monkeypatch.setattr(
        router_module,
        "classify_and_route",
        lambda _query, _mode_hint: {
            "agent_name": "default_llm_agent",
            "reason": "test",
            "intent": "chat",
            "_prompt_versions": [prompt_version],
        },
    )

    result = await router_module.router_node(
        {
            "query": "普通问题",
            "mode_hint": None,
            "force_route": None,
            "metadata": {"prompt_versions": []},
        }
    )

    assert result["route"] == "default"
    assert result["metadata"]["prompt_versions"] == [prompt_version]
    assert "_prompt_versions" not in result["metadata"]["route"]


class _FakeExecutorLLM:
    calls = 0

    def __init__(self, **_kwargs):
        pass

    def invoke(self, _prompt):
        type(self).calls += 1
        if type(self).calls == 1:
            return SimpleNamespace(content="get_lunar_chart")
        return SimpleNamespace(
            content=(
                '{"birth_date":"2001-05-14","birth_time":"16:05",'
                '"gender":"男","birthplace":"绍兴"}'
            )
        )

    async def ainvoke(self, prompt):
        return self.invoke(prompt)


class _FakeToolRegistry:
    def capabilities(self):
        return [
            {
                "name": "get_lunar_chart",
                "description": "生成八字和农历排盘。",
            }
        ]

    async def execute(self, name, arguments, **_kwargs):
        assert name == "get_lunar_chart"
        assert arguments["birth_date"] == "2001-05-14"
        return "排盘结果"


@pytest.mark.asyncio
async def test_executor_tracks_selection_and_birth_extraction_prompts(monkeypatch):
    _FakeExecutorLLM.calls = 0
    monkeypatch.setattr(executor_module, "ChatTongyi", _FakeExecutorLLM)
    monkeypatch.setattr(
        executor_module,
        "get_tool_registry",
        lambda: _FakeToolRegistry(),
    )

    result = await executor_module.executor_node(
        {
            "query": "分析出生信息",
            "plan_tasks": ["生成八字排盘"],
            "plan_completed": [],
            "plan_notes": [],
            "plan_iteration": 0,
            "metadata": {"prompt_versions": []},
            "context": "",
        }
    )

    versions = result["metadata"]["prompt_versions"]
    assert [entry["stage"] for entry in versions] == [
        "executor_tool_selection",
        "executor_birth_extract",
    ]
    assert all(entry["iteration"] == 1 for entry in versions)
    assert all(entry["rendered_sha256"] for entry in versions)

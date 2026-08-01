from __future__ import annotations

import json
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import BaseModel, Field

from agent.artifacts import create_citation, create_json_artifact
from agent.capabilities import CapabilityExecutor, SearchCapabilityOutput
from agent.context import context_from_config
from agent.events import emit_capability_event, emit_runtime_event
from agent.models import ModelGateway, ModelMessage, ModelRequest
from agent.specs import prompt_for
from agent.state import RootState
from agent.workflows.common import (
    conversation_messages,
    prompt_metadata,
    require_model_budget,
    stream_model_answer,
)


class ResearchPlan(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=5)
    search_queries: list[str] = Field(default_factory=list, max_length=5)
    search_budget: int | None = Field(default=None, ge=0, le=5)


class EvidenceGrade(BaseModel):
    sufficient: bool
    covered_question_indexes: list[int] = Field(
        default_factory=list,
        max_length=5,
    )
    gaps: list[str] = Field(default_factory=list, max_length=5)
    supplemental_search_queries: list[str] = Field(
        default_factory=list,
        max_length=5,
    )
    assessment: str = Field(default="", max_length=500)


def _unique_queries(
    queries: list[str],
    *,
    excluding: list[str] | None = None,
) -> list[str]:
    seen = {
        item.strip().casefold()
        for item in (excluding or [])
        if item.strip()
    }
    result: list[str] = []
    for raw_query in queries:
        query = raw_query.strip()
        normalized = query.casefold()
        if not query or normalized in seen:
            continue
        seen.add(normalized)
        result.append(query)
    return result


def _valid_covered_indexes(
    indexes: list[int],
    *,
    question_count: int,
) -> list[int]:
    return sorted(
        {
            index
            for index in indexes
            if type(index) is int and 0 <= index < question_count
        }
    )


def build_research_workflow(
    gateway: ModelGateway,
    capability_executor: CapabilityExecutor,
):
    async def plan(state: RootState):
        model_calls = require_model_budget(state)
        prompt_path = prompt_for(state["prompt_bundle"], "plan")
        system_prompt, metadata = prompt_metadata(
            state,
            stage="research.plan",
            prompt_path=prompt_path,
        )
        plan_result = await gateway.structured(
            state["model_profile"],
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=system_prompt),
                    *conversation_messages(state),
                    ModelMessage(role="user", content=state["query"]),
                ]
            ),
            ResearchPlan,
            stage="research.plan",
        )
        candidate_queries = _unique_queries(plan_result.search_queries)
        search_budget = (
            plan_result.search_budget
            if plan_result.search_budget is not None
            else len(candidate_queries)
        )
        initial_queries = candidate_queries[:search_budget]
        normalized_plan = {
            **plan_result.model_dump(),
            "search_queries": initial_queries,
            "search_budget": search_budget,
        }
        emit_runtime_event(
            "progress",
            stage="research.plan",
            questions=len(plan_result.questions),
            search_queries=len(initial_queries),
            search_budget=search_budget,
        )
        return {
            "research_plan": normalized_plan,
            "pending_search_queries": initial_queries,
            "model_calls": model_calls,
            "metadata": metadata,
        }

    async def dispatch_research_tasks(state: RootState):
        return {"research_round": state.get("research_round", 0) + 1}

    def fan_out_searches(state: RootState):
        remaining_budget = max(
            0,
            state["max_tool_calls"] - state.get("tool_calls", 0),
        )
        queries = _unique_queries(
            state.get("pending_search_queries", []),
            excluding=state.get("attempted_search_queries", []),
        )[: min(5, remaining_budget)]
        if not queries:
            return "join_evidence"
        return [
            Send(
                "search_evidence",
                {
                    "query": state["query"],
                    "search_query": query,
                    "search_index": index,
                    "research_round": state["research_round"],
                    "allowed_capabilities": state["allowed_capabilities"],
                    "execution_id": state["execution_id"],
                    "shadow": state["shadow"],
                },
            )
            for index, query in enumerate(queries)
        ]

    async def search_evidence(
        state: RootState,
        config: RunnableConfig,
    ):
        run_context = context_from_config(config)
        query = state["search_query"]
        index = state["search_index"]
        research_round = state["research_round"]
        try:
            result = await capability_executor.execute(
                "web_search",
                {"query": query, "max_results": 5},
                context=run_context,
                allowed_capabilities=state["allowed_capabilities"],
                stage="research.collect",
                event_sink=emit_capability_event,
                event_metadata={
                    "index": index,
                    "round": research_round,
                },
            )
            output = result.output
            items = (
                output.items
                if isinstance(output, SearchCapabilityOutput)
                else []
            )
            citations = [
                create_citation(
                    title=item.title,
                    url=item.url,
                    snippet=item.snippet,
                ).model_dump(mode="json")
                for item in items
            ]
            evidence = {
                "query": query,
                "content": "\n".join(
                    f"- {item.title}: {item.snippet} ({item.url})"
                    for item in items
                ),
                "citations": citations,
                "capability_idempotency_key": result.idempotency_key,
                "round": research_round,
            }
            succeeded = bool(evidence["content"])
        except Exception as exc:
            citations = []
            evidence = {
                "query": query,
                "content": "",
                "error_code": type(exc).__name__,
                "round": research_round,
            }
            succeeded = False
        emit_runtime_event(
            "progress",
            stage="research.collect",
            round=research_round,
            index=index,
            attempted=1,
            succeeded=int(succeeded),
            failed=int(not succeeded),
            sources=len(citations),
            degraded=not succeeded,
        )
        return {
            "evidence": [evidence],
            "citations": citations,
            "attempted_search_queries": [query],
            "tool_calls": 1,
        }

    async def join_evidence(
        state: RootState,
        config: RunnableConfig,
    ):
        await context_from_config(config).ensure_active()
        research_round = state.get("research_round", 0)
        round_evidence = [
            item
            for item in state.get("evidence", [])
            if item.get("round") == research_round
        ]
        succeeded = sum(bool(item.get("content")) for item in round_evidence)
        failed = len(round_evidence) - succeeded
        unique_citations = {
            item["citation_id"]: item
            for item in state.get("citations", [])
        }
        emit_runtime_event(
            "progress",
            stage="research.collect",
            round=research_round,
            attempted=len(round_evidence),
            succeeded=succeeded,
            failed=failed,
            total_sources=len(unique_citations),
            degraded=failed > 0,
        )
        return {"pending_search_queries": []}

    async def grade_evidence(
        state: RootState,
        config: RunnableConfig,
    ):
        await context_from_config(config).ensure_active()
        question_count = len(
            state.get("research_plan", {}).get("questions", [])
        )
        unique_citations = {
            item["citation_id"]: item
            for item in state.get("citations", [])
        }
        source_count = len(unique_citations)
        model_calls_used = state.get("model_calls", 0)

        if (
            state.get("research_plan", {}).get("search_budget") == 0
            and not state.get("attempted_search_queries")
        ):
            grade = {
                "sufficient": True,
                "model_assessment_sufficient": True,
                "covered_question_indexes": list(range(question_count)),
                "gaps": [],
                "supplemental_search_queries": [],
                "assessment": "该目标无需外部检索。",
                "source_count": 0,
                "minimum_sources": 0,
                "coverage_complete": True,
                "exhausted_reason": None,
            }
            emit_runtime_event(
                "progress",
                stage="research.grade",
                round=state.get("research_round", 0),
                sufficient=True,
                covered_questions=question_count,
                total_questions=question_count,
                unique_sources=0,
                minimum_sources=0,
                will_supplement=False,
                exhausted_reason=None,
            )
            return {
                "evidence_grade": grade,
                "pending_search_queries": [],
            }

        # The final synthesis must always retain one model call.
        if model_calls_used >= state["max_model_calls"] - 1:
            grade = {
                "sufficient": False,
                "model_assessment_sufficient": False,
                "covered_question_indexes": [],
                "gaps": ["模型调用预算不足，无法继续评估证据。"],
                "supplemental_search_queries": [],
                "assessment": "",
                "source_count": source_count,
                "exhausted_reason": "model_budget_reserved_for_synthesis",
            }
            emit_runtime_event(
                "progress",
                stage="research.grade",
                round=state.get("research_round", 0),
                sufficient=False,
                covered_questions=0,
                total_questions=question_count,
                unique_sources=source_count,
                will_supplement=False,
                exhausted_reason=grade["exhausted_reason"],
            )
            return {
                "evidence_grade": grade,
                "pending_search_queries": [],
            }

        model_calls = require_model_budget(state)
        prompt_path = prompt_for(state["prompt_bundle"], "grade")
        system_prompt, metadata = prompt_metadata(
            state,
            stage="research.grade",
            prompt_path=prompt_path,
        )
        grade_input = {
            "user_query": state["query"],
            "questions": state.get("research_plan", {}).get(
                "questions",
                [],
            ),
            "evidence": [
                {
                    "query": item.get("query", ""),
                    "content": item.get("content", ""),
                    "error_code": item.get("error_code"),
                }
                for item in state.get("evidence", [])
            ],
        }
        result = await gateway.structured(
            state["model_profile"],
            ModelRequest(
                messages=[
                    ModelMessage(role="system", content=system_prompt),
                    ModelMessage(
                        role="user",
                        content=json.dumps(grade_input, ensure_ascii=False),
                    ),
                ]
            ),
            EvidenceGrade,
            stage="research.grade",
        )

        covered = _valid_covered_indexes(
            result.covered_question_indexes,
            question_count=question_count,
        )
        minimum_sources = min(2, max(1, question_count))
        coverage_complete = len(covered) == question_count
        enough_sources = source_count >= minimum_sources
        sufficient = (
            result.sufficient
            and coverage_complete
            and enough_sources
        )
        remaining_tool_calls = max(
            0,
            state["max_tool_calls"] - state.get("tool_calls", 0),
        )
        supplemental_queries = _unique_queries(
            result.supplemental_search_queries,
            excluding=state.get("attempted_search_queries", []),
        )[:remaining_tool_calls]
        remaining_model_calls = state["max_model_calls"] - model_calls
        will_supplement = (
            not sufficient
            and bool(supplemental_queries)
            and remaining_tool_calls > 0
            and remaining_model_calls >= 2
        )

        exhausted_reason = None
        if not sufficient and not will_supplement:
            if remaining_tool_calls == 0:
                exhausted_reason = "tool_budget_exhausted"
            elif remaining_model_calls < 2:
                exhausted_reason = "model_budget_reserved_for_synthesis"
            else:
                exhausted_reason = "no_new_supplemental_queries"

        grade = {
            **result.model_dump(),
            "sufficient": sufficient,
            "model_assessment_sufficient": result.sufficient,
            "covered_question_indexes": covered,
            "source_count": source_count,
            "minimum_sources": minimum_sources,
            "coverage_complete": coverage_complete,
            "exhausted_reason": exhausted_reason,
        }
        emit_runtime_event(
            "progress",
            stage="research.grade",
            round=state.get("research_round", 0),
            sufficient=sufficient,
            covered_questions=len(covered),
            total_questions=question_count,
            unique_sources=source_count,
            minimum_sources=minimum_sources,
            will_supplement=will_supplement,
            exhausted_reason=exhausted_reason,
        )
        return {
            "evidence_grade": grade,
            "pending_search_queries": (
                supplemental_queries if will_supplement else []
            ),
            "model_calls": model_calls,
            "metadata": metadata,
        }

    def route_after_grade(
        state: RootState,
    ) -> Literal["supplement", "finalize"]:
        if state.get("pending_search_queries"):
            return "supplement"
        return "finalize"

    async def finalize_evidence(
        state: RootState,
        config: RunnableConfig,
    ):
        run_context = context_from_config(config)
        evidence = state.get("evidence", [])
        citations = list(
            {
                item["citation_id"]: item
                for item in state.get("citations", [])
            }.values()
        )
        succeeded = sum(bool(item.get("content")) for item in evidence)
        failed = len(evidence) - succeeded
        artifact = create_json_artifact(
            artifact_type="research_evidence",
            value={
                "queries": evidence,
                "citations": citations,
                "grade": state.get("evidence_grade", {}),
            },
            metadata={
                "attempted": len(evidence),
                "succeeded": succeeded,
                "failed": failed,
                "rounds": state.get("research_round", 0),
                "sufficient": bool(
                    state.get("evidence_grade", {}).get("sufficient")
                ),
            },
        )
        await run_context.stage_artifact(artifact)
        emit_runtime_event(
            "artifact.created",
            **artifact.ref.model_dump(mode="json"),
            citation_count=len(citations),
        )
        for sequence, citation in enumerate(citations, start=1):
            emit_runtime_event(
                "citation.created",
                **citation,
                artifact_id=artifact.ref.artifact_id,
                sequence=sequence,
            )
        return {
            "artifacts": [
                *state.get("artifacts", []),
                artifact.model_dump(mode="json"),
            ],
        }

    async def synthesize(state: RootState):
        plan_value = state.get("research_plan", {})
        evidence = state.get("evidence", [])
        context_parts = [
            "【研究问题】",
            *[f"- {item}" for item in plan_value.get("questions", [])],
            "【检索证据】",
        ]
        has_evidence = False
        for item in evidence:
            if item.get("content"):
                has_evidence = True
                context_parts.append(
                    f"检索词：{item['query']}\n{item['content']}"
                )
        if (
            not has_evidence
            and plan_value.get("search_budget") == 0
        ):
            context_parts.append(
                "研究计划判断本题无需外部检索；不要声称已经联网或提供外部引用。"
            )
        elif not has_evidence:
            context_parts.append("没有获得外部检索结果，请明确说明不确定性。")
        grade = state.get("evidence_grade", {})
        if not grade.get("sufficient"):
            gaps = grade.get("gaps", [])
            context_parts.append(
                "【证据限制】\n"
                + (
                    "\n".join(f"- {item}" for item in gaps)
                    if gaps
                    else "- 证据未达到完整性阈值。"
                )
            )
        citations = list(
            {
                item["citation_id"]: item
                for item in state.get("citations", [])
            }.values()
        )
        if citations:
            context_parts.append(
                "【引用编号】\n"
                + "\n".join(
                    f"[{item['citation_id']}] {item['title']} {item['url']}"
                    for item in citations
                )
            )
        return await stream_model_answer(
            gateway=gateway,
            state=state,
            profile_name=state["model_profile"],
            stage="research.synthesize",
            prompt_path=prompt_for(state["prompt_bundle"], "generate"),
            context="\n\n".join(context_parts),
        )

    graph = StateGraph(RootState)
    graph.add_node("structured_plan", plan)
    graph.add_node("dispatch_research_tasks", dispatch_research_tasks)
    graph.add_node("search_evidence", search_evidence)
    graph.add_node("join_evidence", join_evidence)
    graph.add_node("grade_evidence", grade_evidence)
    graph.add_node("finalize_evidence", finalize_evidence)
    graph.add_node("synthesize", synthesize)
    graph.add_edge(START, "structured_plan")
    graph.add_edge("structured_plan", "dispatch_research_tasks")
    graph.add_conditional_edges(
        "dispatch_research_tasks",
        fan_out_searches,
        ["search_evidence", "join_evidence"],
    )
    graph.add_edge("search_evidence", "join_evidence")
    graph.add_edge("join_evidence", "grade_evidence")
    graph.add_conditional_edges(
        "grade_evidence",
        route_after_grade,
        {
            "supplement": "dispatch_research_tasks",
            "finalize": "finalize_evidence",
        },
    )
    graph.add_edge("finalize_evidence", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile(name="research_v1")

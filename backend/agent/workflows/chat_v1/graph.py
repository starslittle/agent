from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.models import ModelGateway
from agent.specs import prompt_for
from agent.state import RootState
from agent.workflows.common import stream_model_answer


def build_chat_workflow(gateway: ModelGateway):
    async def model_stream(state: RootState):
        return await stream_model_answer(
            gateway=gateway,
            state=state,
            profile_name=state["model_profile"],
            stage="chat.generate",
            prompt_path=prompt_for(state["prompt_bundle"], "generate"),
        )

    graph = StateGraph(RootState)
    graph.add_node("model_stream", model_stream)
    graph.add_edge(START, "model_stream")
    graph.add_edge("model_stream", END)
    return graph.compile(name="chat_v1")

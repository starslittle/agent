"""常规LLM节点 - 直接对话模式"""

import sys
from typing import Dict, Any
from graph.state import GraphState
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from agent.prompts import append_prompt_version, load_prompt
from app.core.settings import settings


def _safe_preview(text: str, limit: int = 100) -> str:
    """避免 Windows GBK 控制台因 emoji 等字符打印失败。"""
    s = (text or "")[:limit]
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    return s.encode(encoding, errors="replace").decode(encoding, errors="replace")


async def direct_llm_node(state: GraphState) -> Dict[str, Any]:
    """
    常规LLM节点：简单的直接对话，不使用工具
    适用于日常聊天、简单问答

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 final_answer
    """
    query = state.get("query", "")
    chat_history = state.get("chat_history", [])

    print(f"\n[Direct LLM] 处理查询: {query[:50]}...")

    try:
        # 创建LLM
        llm = ChatTongyi(
            model=settings.LLM_MODEL_NAME or "deepseek-v4-flash",
            temperature=0.2,
            dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
        )

        prompt_path = "agent/prompts/direct_llm_system.txt"
        system_prompt = load_prompt(prompt_path)
        state = append_prompt_version(
            state,
            stage="direct_llm_compatibility",
            relative_path=prompt_path,
            rendered_prompt=system_prompt,
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{query}")
        ])

        # 转换聊天历史格式
        messages = []
        for role, content in chat_history:
            if role == "human":
                messages.append(("human", content))
            elif role == "ai":
                messages.append(("ai", content))

        # 调用LLM
        chain = prompt | llm
        response = await chain.ainvoke({
            "query": query,
            "chat_history": messages
        })

        answer = response.content if hasattr(response, 'content') else str(response)

        print(f"[Direct LLM] 生成答案: {_safe_preview(answer)}...")

        return {
            **state,
            "final_answer": answer,
            "output": answer,
        }

    except Exception as e:
        print(f"[Direct LLM] 错误: {e}")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "final_answer": f"抱歉，处理您的请求时出错：{str(e)}",
            "output": f"抱歉，处理您的请求时出错：{str(e)}",
            "error": str(e),
        }

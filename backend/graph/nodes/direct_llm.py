"""常规LLM节点 - 直接对话模式"""

from typing import Dict, Any
from graph.state import GraphState
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.core.settings import settings


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

    print(f"\n[💬 Direct LLM] 处理查询: {query[:50]}...")

    try:
        # 创建LLM
        llm = ChatTongyi(
            model="qwen-plus-2025-07-28",
            temperature=0.2,
            dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
        )

        # 构建prompt
        system_prompt = """你是中文助理，请用简洁、准确的中文回答用户问题。

遵循以下原则：
1. 使用简体中文回答
2. 保持友好和专业的语气
3. 如果不知道答案，诚实告知
4. 避免重复和啰嗦
"""

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
            "chat_history": messages if messages else None
        })

        answer = response.content if hasattr(response, 'content') else str(response)

        print(f"[💬 Direct LLM] 生成答案: {answer[:100]}...")

        return {
            **state,
            "final_answer": answer,
            "output": answer,
        }

    except Exception as e:
        print(f"[❌ Direct LLM] 错误: {e}")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "final_answer": f"抱歉，处理您的请求时出错：{str(e)}",
            "output": f"抱歉，处理您的请求时出错：{str(e)}",
            "error": str(e),
        }

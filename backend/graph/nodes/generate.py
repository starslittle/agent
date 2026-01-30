"""生成节点 - 整合上下文生成最终答案"""

from typing import Dict, Any
from graph.state import GraphState
from langchain_community.chat_models import ChatTongyi
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.core.settings import settings


async def generate_node(state: GraphState) -> Dict[str, Any]:
    """
    生成节点：整合上下文和工具结果，生成最终答案
    - 优先使用工具结果
    - 其次使用RAG上下文
    - 最后使用LLM生成答案

    Args:
        state: 当前状态

    Returns:
        Dict: 更新后的状态，包含 final_answer
    """
    query = state.get("query", "")
    route = state.get("route", "")
    context = state.get("context", "")
    tool_results = state.get("tool_results", {})
    chat_history = state.get("chat_history", [])

    print(f"\n[✨ Generate] 生成最终答案，模式: {route}")

    try:
        # 创建LLM
        llm = ChatTongyi(
            model="qwen-plus-2025-07-28",
            temperature=0.2,
            dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
        )

        # 根据模式构建prompt
        if route == "fortune":
            system_prompt = """你是专业的命理分析师，精通紫微斗数、八字命理等。

请基于提供的命理知识，为用户进行专业的命理分析：
1. 保持专业、客观的态度
2. 基于检索到的知识进行分析
3. 给出合理的建议和指导
4. 使用简体中文回答
"""

        elif route == "research":
            system_prompt = """你是专业的研究分析师，擅长深入研究和综合分析。

请基于检索到的资料和工具结果，为用户提供深入的分析：
1. 整合多个来源的信息
2. 提供全面、深入的分析
3. 给出有见地的结论
4. 使用简体中文回答
"""

        else:
            system_prompt = """你是智能助理，请为用户提供准确、有用的回答。

请基于可用的信息回答用户问题：
1. 如果有工具结果，优先参考
2. 如果有检索上下文，结合上下文回答
3. 保持准确和有用
4. 使用简体中文回答
"""

        # 构建上下文信息
        context_parts = []

        # 添加工具结果
        if tool_results:
            context_parts.append("【工具执行结果】")
            for tool_name, result in tool_results.items():
                if not tool_name.endswith("_error"):
                    context_parts.append(f"{tool_name}: {str(result)[:200]}")

        # 添加RAG上下文
        if context:
            context_parts.append("【检索到的相关内容】")
            context_parts.append(context)

        # 组合最终上下文
        full_context = "\n\n".join(context_parts) if context_parts else "无额外信息"

        # 构建prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "用户问题：{query}\n\n参考信息：\n{context}\n\n请基于以上信息回答用户问题。")
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
            "context": full_context,
            "chat_history": messages if messages else None
        })

        answer = response.content if hasattr(response, 'content') else str(response)

        print(f"[✨ Generate] 生成答案: {answer[:100]}...")

        return {
            **state,
            "final_answer": answer,
            "output": answer,
        }

    except Exception as e:
        print(f"[❌ Generate] 错误: {e}")
        import traceback
        traceback.print_exc()

        return {
            **state,
            "final_answer": f"抱歉，生成答案时出错：{str(e)}",
            "output": f"抱歉，生成答案时出错：{str(e)}",
            "error": str(e),
        }

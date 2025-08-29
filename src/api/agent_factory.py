from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from langchain.agents import AgentExecutor, create_react_agent  # type: ignore
from langchain import hub  # type: ignore
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder  # type: ignore
from langchain_community.chat_models import ChatTongyi  # type: ignore
from langchain_core.messages import AIMessage  # type: ignore
from langchain_core.runnables import RunnableLambda  # type: ignore
from src.core.settings import settings
from langchain_community.tools.tavily_search import TavilySearchResults  # type: ignore
from langchain.tools.retriever import create_retriever_tool  # type: ignore
from langchain_community.vectorstores import Chroma  # type: ignore
from langchain_community.embeddings import HuggingFaceBgeEmbeddings  # type: ignore
from langchain_community.retrievers import BM25Retriever  # type: ignore
from langchain_core.documents import Document  # type: ignore
from langchain.schema.agent import AgentFinish
from langchain_core.exceptions import OutputParserException

from ..rag.hybrid_retriever import HybridRetriever, CrossEncoderReranker
from ..agent_app.tools import (
    get_current_date,
    get_seniverse_weather,
    init_notion_rag,
    query_notion_kb,
    init_pandas_rag,
    query_pandas_data,
    init_local_rag,
    query_local_kb,
    deep_research,
)


API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parents[1]


def _handle_parsing_error(error: OutputParserException) -> AgentFinish:
    """自定义解析错误处理器，向前端返回更友好的信息。"""
    error_text = str(error)
    # 提取LLM的原始输出，这是最关键的信息
    llm_output = getattr(error, 'llm_output', '')

    # 检查是否是“答案和动作并存”的常见错误
    if "Parsing LLM output produced both a final answer and a parse-able action" in error_text:
        # 尝试从原始文本中智能提取 Final Answer
        # Final Answer 通常是日志的最后一部分
        try:
            # 健壮地分割字符串，防止 "Final Answer:" 不存在时出错
            parts = llm_output.split("Final Answer:")
            if len(parts) > 1:
                final_answer = parts[-1].strip()
                if final_answer:
                    # 如果成功提取，就用它作为最终输出
                    return AgentFinish(return_values={"output": final_answer}, log=error_text)
        except Exception:
            # 如果解析失败，则回退到下面的通用错误消息
            pass
        
        # 如果无法提取，返回一个更友好的通用提示
        response = "模型返回了模糊的响应（同时包含答案和操作），无法自动解析。请您尝试简化问题或调整提问方式。"
    
    else:
        # 对于其他未知解析错误，只显示错误摘要，避免暴露过多内部细节
        response = f"模型输出格式无法解析，请稍后重试。"
    
    # 对于无法自动恢复的错误，包装成 AgentFinish 对象，确保链能正常结束
    return AgentFinish(return_values={"output": response}, log=error_text)


def load_prompt_template(path: str) -> ChatPromptTemplate:
    candidate_paths: list[Path] = []
    p = Path(path)
    if p.is_absolute():
        candidate_paths = [p]
    else:
        candidate_paths = [
            p,
            (API_DIR / p),
            (PROJECT_ROOT / p),
            (PROJECT_ROOT / "backend" / p),                    # 兼容 backend 相对路径
            (PROJECT_ROOT / "backend" / "prompts" / p.name), # 兼容旧 prompts 目录
        ]
        if p.parent == Path(""):
            candidate_paths.append(API_DIR / "prompts" / p.name)

    file_path: Path | None = None
    for cp in candidate_paths:
        try:
            if cp.exists():
                file_path = cp
                break
        except Exception:
            continue
    if file_path is None:
        tried = " | ".join(str(x) for x in candidate_paths)
        raise FileNotFoundError(f"Prompt 文件未找到: {path}. 尝试路径: {tried}")

    text = file_path.read_text(encoding="utf-8")
    react_format_rules = (
        "\n\n"
        "You MUST follow this exact ReAct schema with ASCII colons ':':\n"
        "- When using a tool:\n"
        "Thought: <your reasoning>\n"
        "Action: <one of the tool names exactly>\n"
        "Action Input: <JSON input for the tool>\n"
        "- When you can answer directly (no tool):\n"
        "Thought: <your reasoning>\n"
        "Final Answer: <your final answer>\n"
        "Notes: Use 'Action:' not 'Action：'. Use 'Action Input:' not 'Action Input：'.\n"
        "Do not add any extra keys or text before/after these lines."
    )
    tools_hint = (
        "\n\nAvailable tools (use exactly one name in Action):\n"
        "{tools}\n\n"
        "You can only choose from: {tool_names}\n"
    )
    text = text + tools_hint + react_format_rules
    prompt = ChatPromptTemplate.from_messages([
        ("system", text),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}\n\n{agent_scratchpad}"),
    ])
    return prompt


def load_tool(name: str):
    key = name.strip().lower()
    if key in {"tavily", "tavily_search_results_json"}:
        return TavilySearchResults(max_results=5)
    if key == "get_current_date":
        return get_current_date
    if key == "get_seniverse_weather":
        return get_seniverse_weather
    if key == "init_notion_rag":
        return init_notion_rag
    if key == "query_notion_kb":
        return query_notion_kb
    if key == "init_pandas_rag":
        return init_pandas_rag
    if key == "query_pandas_data":
        return query_pandas_data
    if key == "init_local_rag":
        return init_local_rag
    if key == "query_local_kb":
        return query_local_kb
    if key == "deep_research":
        return deep_research
    raise ValueError(f"未知工具: {name}")


def create_retriever(config: Dict[str, Any]):
    persist_dir = config.get("rag_db_path", "./storage/chroma/local")
    collection_name = config.get("collection_name", "local")
    top_k = int(config.get("top_k", 8))

    embeddings = HuggingFaceBgeEmbeddings(
        model_name="BAAI/bge-small-zh-v1.5",
        encode_kwargs={"normalize_embeddings": True},
    )
    vectordb = Chroma(
        embedding_function=embeddings,
        persist_directory=persist_dir,
        collection_name=collection_name,
    )
    vector_retriever = vectordb.as_retriever(
        search_type="mmr", search_kwargs={"k": top_k, "lambda_mult": 0.5}
    )

    bm25: BM25Retriever | None = None
    try:
        sample_docs = [
            Document(page_content=t[0]) for t in vectordb.get(include=["documents"])[:200]  # type: ignore
        ]
        if sample_docs:
            bm25 = BM25Retriever.from_documents(sample_docs)
            bm25.k = top_k
    except Exception:
        bm25 = None

    reranker: CrossEncoderReranker | None = None
    if bool(config.get("rerank", True)):
        try:
            reranker = CrossEncoderReranker("BAAI/bge-reranker-large", top_n=min(3, top_k))
        except Exception:
            reranker = None

    if bm25 is not None:
        return HybridRetriever(
            vector_retriever=vector_retriever,
            others=[bm25],
            fetch_k_each=top_k,
            final_top_k=top_k,
            reranker=reranker,
        )
    return HybridRetriever(
        vector_retriever=vector_retriever,
        others=[],
        fetch_k_each=top_k,
        final_top_k=top_k,
        reranker=reranker,
    )


def create_agent_from_config(config: Dict[str, Any], streaming_override: bool | None = None) -> AgentExecutor:
    model_name = (config.get("llm") or "qwen-turbo-2025-07-15").strip()
    api_key = settings.DASHSCOPE_API_KEY or ""
    if not api_key:
        print("[WARNING] DASHSCOPE_API_KEY 未设置，禁用流式模式（Agent 将使用非流式）")

    use_streaming = bool(streaming_override) if streaming_override is not None else False

    base_llm = ChatTongyi(
        model=model_name,
        temperature=0.2,
        dashscope_api_key=api_key,
        streaming=use_streaming,
    )
    # 在模型层增加安全兜底：当上游 SDK 抛错（如 KeyError 'request'）时，回退到固定输出
    # 固定输出遵循 ReAct 最终答案格式，便于解析
    fallback = RunnableLambda(lambda _: AIMessage(content="Final Answer: 模型服务暂时不可用，请稍后再试。"))
    llm = base_llm.with_fallbacks([fallback])

    # Direct LLM 模式：不使用 ReAct/工具，走简单问答（可选注入上下文与历史）
    mode = str(config.get("mode", "")).strip().lower()
    if mode in {"direct", "simple", "llm"}:
        system_text = (
            str(config.get("system_prompt") or "你是中文助手，请用简洁、准确的中文回答用户问题。如有提供上下文，可结合其作答。")
            .strip()
        )
        direct_prompt = ChatPromptTemplate.from_messages([
            ("system", system_text),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}\n\n{context}"),
        ])

        direct_chain = direct_prompt | llm

        class DirectExecutor:
            def __init__(self, chain):
                self._chain = chain

            def invoke(self, params: Dict[str, Any]):
                res = self._chain.invoke(
                    {
                        "input": params.get("input", ""),
                        "context": params.get("context", ""),
                        "chat_history": params.get("chat_history"),
                    }
                )
                content = getattr(res, "content", None)
                if content is None:
                    content = str(res)
                return {"output": str(content)}

            def stream(self, params: Dict[str, Any]):
                accumulated = ""
                for chunk in self._chain.stream(
                    {
                        "input": params.get("input", ""),
                        "context": params.get("context", ""),
                        "chat_history": params.get("chat_history"),
                    }
                ):
                    try:
                        piece = getattr(chunk, "content", None)
                        if piece is None:
                            # 兼容部分实现返回 dict / message
                            piece = getattr(getattr(chunk, "message", object()), "content", "")
                            if not piece and isinstance(chunk, dict):
                                piece = str(chunk.get("content", ""))
                        if piece:
                            accumulated += str(piece)
                            yield {"output": accumulated}
                    except Exception:
                        continue

        return DirectExecutor(direct_chain)

    tool_names: List[str] = config.get("tools", [])
    tools = [load_tool(n) for n in tool_names]

    if config.get("rag_db_path"):
        retriever = create_retriever(config)
        rag_tool = create_retriever_tool(
            retriever,
            name="rag_search",
            description="基于向量知识库的检索工具（占位符示例）。",
        )
        tools.append(rag_tool)

    prompt_path = config.get("prompt_template_path")
    if not prompt_path:
        prompt = hub.pull("hwchase17/react")
    else:
        prompt = load_prompt_template(prompt_path)

    agent = create_react_agent(llm, tools, prompt)
    
    # 从配置中读取迭代次数和执行时间限制，如果没有配置则使用默认值
    max_iterations = config.get("max_iterations", 8)
    max_execution_time = config.get("max_execution_time", 60)
    
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=_handle_parsing_error,
        max_iterations=max_iterations,
        max_execution_time=max_execution_time,
        stream_runnable=use_streaming,
    )
    return executor



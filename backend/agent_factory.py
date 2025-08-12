"""
Agent 工厂：根据 YAML 配置动态构建 AgentExecutor。

设计目标：
- 配置驱动开发（Open-Closed）：新增/修改 Agent 仅需改 YAML 与 Prompt 文件；
- 动态装配：按工具名加载工具；存在 rag_db_path 时自动封装检索器工具；
- 与 FastAPI 解耦：工厂只负责创建 AgentExecutor 实例。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import sys

# 将项目根下的 src 目录加入 sys.path，便于以顶层包名导入（rag、agent_app）
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from langchain.agents import AgentExecutor, create_react_agent
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatTongyi
# Tavily 工具在 LangChain 社区版中提供
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.tools.retriever import create_retriever_tool
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

from rag.hybrid_retriever import HybridRetriever, CrossEncoderReranker

from agent_app.tools import (  # type: ignore
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


def load_prompt_template(path: str) -> ChatPromptTemplate:
    """从文件加载 ReAct 风格模板，并注入 tools/tool_names 占位符。

    会按以下顺序解析相对路径：
    1) 进程当前工作目录下的相对路径
    2) backend/ 目录下
    3) 仓库根目录下
    常见用法：传入 "prompts/general_prompt.txt"（位于 backend/prompts/ 下）
    """
    candidate_paths = []
    p = Path(path)
    if p.is_absolute():
        candidate_paths = [p]
    else:
        candidate_paths = [
            p,
            (BACKEND_DIR / p),
            (PROJECT_ROOT / p),
        ]
        # 若仅给了文件名，尝试在 backend/prompts/ 下查找
        if p.parent == Path(""):
            candidate_paths.append(BACKEND_DIR / "prompts" / p.name)

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
    # 强化 ReAct 输出格式，避免中文标点导致解析失败
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
    # 注入工具占位符，满足 create_react_agent 对 {tools}/{tool_names} 的要求
    tools_hint = (
        "\n\nAvailable tools (use exactly one name in Action):\n"
        "{tools}\n\n"
        "You can only choose from: {tool_names}\n"
    )
    text = text + tools_hint + react_format_rules
    # 兼容不同版本 LangChain：将 agent_scratchpad 作为字符串插入 human 消息
    prompt = ChatPromptTemplate.from_messages([
        ("system", text),
        ("human", "{input}\n\n{agent_scratchpad}"),
    ])
    return prompt


def load_tool(name: str):
    """按名称加载工具对象。

    目前支持：
    - "tavily_search_results_json": TavilySearchResults(max_results=5)
    可扩展：在此增加更多 name → Tool 的映射。
    """
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
    """真实检索器：Chroma 向量检索 + 可选 BM25 + 交叉重排，统一返回 HybridRetriever。

    要求 rag_db_path 指向 Chroma 的 persist_directory；collection_name 与写入阶段一致。
    """
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
    vector_retriever = vectordb.as_retriever(search_type="mmr", search_kwargs={"k": top_k, "lambda_mult": 0.5})

    # 可选：本地 BM25（基于 vectorstore 中的 texts 构建一个简单检索器）
    bm25: BM25Retriever | None = None
    try:
        # 从 Chroma 拉取部分文档构建 BM25（演示用途，生产建议离线构建）
        sample_docs = [Document(page_content=t[0]) for t in vectordb.get(include=["documents"])[:200]]  # type: ignore
        if sample_docs:
            bm25 = BM25Retriever.from_documents(sample_docs)
            bm25.k = top_k
    except Exception:
        bm25 = None

    # 交叉重排（可选）
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


def create_agent_from_config(config: Dict[str, Any]) -> AgentExecutor:
    """根据单个 agent 的配置字典构建 AgentExecutor。

    要求 config 包含：
    - llm: LLM 模型名（如 qwen-turbo / qwen-plus / gpt-4-turbo-preview）
    - tools: 工具名列表
    - prompt_template_path: Prompt 文件路径
    - 可选 rag_db_path: 用于创建检索器工具
    """
    # 1) LLM
    model_name = (config.get("llm") or "qwen-turbo").strip()
    # 统一用通义千问；如需 OpenAI，可在这里分支
    llm = ChatTongyi(model=model_name, temperature=0.2, dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""))

    # 2) 工具
    tool_names: List[str] = config.get("tools", [])
    tools = [load_tool(n) for n in tool_names]

    # 2.1) 若配置了 RAG，则封装为 retriever 工具
    if config.get("rag_db_path"):
        retriever = create_retriever(config)
        rag_tool = create_retriever_tool(
            retriever,
            name="rag_search",
            description="基于向量知识库的检索工具（占位符示例）。",
        )
        tools.append(rag_tool)

    # 3) Prompt
    prompt_path = config.get("prompt_template_path")
    if not prompt_path:
        # 兜底使用社区 ReAct 提示
        prompt = hub.pull("hwchase17/react")
    else:
        prompt = load_prompt_template(prompt_path)

    # 4) 组装 ReAct Agent
    agent = create_react_agent(llm, tools, prompt)
    # 限制迭代并在解析失败时直接将模型输出作为最终答案，避免无限循环
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors="Final Answer: {text}",
        max_iterations=8,
        max_execution_time=60,
    )
    return executor



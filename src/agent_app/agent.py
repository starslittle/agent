import os
import sys
from pathlib import Path
from src.core.settings import settings
from langchain_community.chat_models import ChatTongyi
from langchain.agents import AgentExecutor, create_react_agent, create_tool_calling_agent
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_tavily import TavilySearch
# 允许将 `src` 作为包根加入模块搜索路径
ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from agent_app.tools import (
    get_current_date,
    get_seniverse_weather,
    init_notion_rag,
    query_notion_kb,
    verify_notion_access,
    init_pandas_rag,
    query_pandas_data,
    init_local_rag,
    query_local_kb,
    deep_research,
)



def main():
    llm = ChatTongyi(model="qwen-turbo-2025-07-15", temperature=0.2, dashscope_api_key=settings.DASHSCOPE_API_KEY)
    tools = [
        TavilySearch(max_results=1),
        get_current_date,
        get_seniverse_weather,
        verify_notion_access,
        init_notion_rag,
        query_notion_kb,
        init_pandas_rag,
        query_pandas_data,
        init_local_rag,
        query_local_kb,
        deep_research,
    ]
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
            你是一个中文助理，具备以下工具：
            - TavilySearch：网页搜索
            - get_current_date：当前日期（中国格式）
            - get_seniverse_weather：中国天气
            - verify_notion_access / init_notion_rag / query_notion_kb：Notion 访问与检索
            - init_pandas_rag / query_pandas_data：CSV 检索与分析
            - init_local_rag / query_local_kb：本地 PDF/TXT 检索

            使用规则（必须遵守）：
            1) 凡是涉及“今天/现在/日期/星期/几号/几月/当前时间”等与时间日期相关的问题，必须调用工具 get_current_date 获取结果，不得凭记忆或模型知识回答。
            2) 事实性问题优先使用工具；无法从工具获得答案时再基于常识推理，但要说明不确定性。
            3) 当用户提到“PDF/本地文件/文件路径/查看xxx.pdf/解析PDF/阅读文档”等需求时，不要说无法访问本地文件，应：先调用 init_local_rag 初始化索引，再调用 query_local_kb 基于检索结果回答。
            4) 当用户提到“CSV/表格/统计/数据分析/文件路径/.csv”等需求时，不要说无法访问本地文件，应：先调用 init_pandas_rag 初始化，再调用 query_pandas_data 进行分析。若用户给出路径，将其视为已在 data/raw 下或由 CSV_* 环境变量指向的路径。
            5) 不得以“无法访问本地文件”为由拒绝。你应当通过已有工具在 data/raw 目录中检索与分析本地内容。
            3) 回答使用简体中文。
            """.strip(),
        ),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    # 构建两套代理：函数调用（稳定）与 ReAct（探索式）
    tc_agent = create_tool_calling_agent(llm, tools, prompt)
    tc_executor = AgentExecutor(agent=tc_agent, tools=tools, verbose=True, stream_runnable=True, handle_parsing_errors=True)

    react_prompt = hub.pull("hwchase17/react-chat")
    react_agent = create_react_agent(llm, tools, react_prompt)
    react_executor = AgentExecutor(agent=react_agent, tools=tools, verbose=True, stream_runnable=True, handle_parsing_errors=True)

    def choose_mode(user_text: str) -> str:
        s = (user_text or "").lower()
        if s.startswith("react:"):
            return "react"
        if s.startswith("tc:") or s.startswith("tool:"):
            return "tc"
        keywords = ["深度检索", "调研", "研究", "综述", "路线", "对比", "方案", "why", "how"]
        if any(k in user_text for k in keywords):
            return "react"
        return "tc"
    print("\nAgent 已准备就绪。输入 'exit' 退出。")
    chat_history = []
    while True:
        q = input("你: ").strip()
        if q.lower() == "exit":
            break
        # 选择代理模式
        mode = choose_mode(q)
        executor = react_executor if mode == "react" else tc_executor
        # 流式输出
        print("智能体:", end="", flush=True)
        final_text = ""
        for chunk in executor.stream({"input": q, "chat_history": chat_history}):
            if isinstance(chunk, dict) and "output" in chunk:
                delta = chunk.get("output")
                print(delta, end="", flush=True)
                final_text += str(delta)
        print()
        chat_history.extend([("human", q), ("ai", final_text)])


if __name__ == "__main__":
    main()

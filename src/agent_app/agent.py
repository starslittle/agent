import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain_community.chat_models import ChatTongyi
from langchain.agents import AgentExecutor, create_tool_calling_agent
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
)

load_dotenv()  # 加载根目录 .env


def main():
    llm = ChatTongyi(model="qwen-turbo", temperature=0.2, dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""))
    tools = [TavilySearch(max_results=1), get_current_date, get_seniverse_weather, verify_notion_access, init_notion_rag, query_notion_kb]
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a helpful assistant with access to web search (Tavily), current date, Chinese weather, Notion access verifier and Notion RAG tools. Prefer tools for factual queries."),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    print("\nAgent 已准备就绪。输入 'exit' 退出。")
    chat_history = []
    while True:
        q = input("你: ").strip()
        if q.lower() == "exit":
            break
        resp = executor.invoke({"input": q, "chat_history": chat_history})
        print("智能体:", resp["output"]) 
        chat_history.extend([("human", q), ("ai", resp["output"])])


if __name__ == "__main__":
    main()

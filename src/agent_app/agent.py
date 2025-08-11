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
        (
            "system",
            """
            你是一个中文助理，具备以下工具：
            - TavilySearch：网页搜索
            - get_current_date：当前日期（中国格式）
            - get_seniverse_weather：中国天气
            - verify_notion_access / init_notion_rag / query_notion_kb：Notion 访问与检索

            使用规则（必须遵守）：
            1) 凡是涉及“今天/现在/日期/星期/几号/几月/当前时间”等与时间日期相关的问题，必须调用工具 get_current_date 获取结果，不得凭记忆或模型知识回答。
            2) 事实性问题优先使用工具；无法从工具获得答案时再基于常识推理，但要说明不确定性。
            3) 回答使用简体中文。
            """.strip(),
        ),
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

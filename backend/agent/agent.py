import asyncio
import sys
from pathlib import Path

from graph import stream_graph
# 允许将 `backend` 作为包根加入模块搜索路径
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def _parse_mode(user_text: str) -> tuple[str | None, str]:
    s = (user_text or "").strip()
    lowered = s.lower()
    if lowered.startswith("fortune:"):
        return "fortune", s[len("fortune:"):].lstrip()
    if lowered.startswith("research:") or lowered.startswith("react:"):
        return "research", s.split(":", 1)[1].lstrip()
    if lowered.startswith("default:") or lowered.startswith("tc:") or lowered.startswith("tool:"):
        return "default", s.split(":", 1)[1].lstrip()
    keywords = ["深度检索", "调研", "研究", "综述", "路线", "对比", "方案", "why", "how"]
    if any(k in s for k in keywords):
        return "research", s
    return "default", s


async def _stream_answer(query: str, chat_history: list, force_route: str | None):
    accumulated = ""
    async for chunk in stream_graph(
        query=query,
        chat_history=chat_history,
        mode_hint=None,
        force_route=force_route,
    ):
        current_output = ""
        if isinstance(chunk, dict):
            current_output = chunk.get("final_answer") or chunk.get("output", "")
        else:
            current_output = str(chunk)
        if current_output and current_output.startswith(accumulated):
            delta = current_output[len(accumulated):]
            if delta:
                print(delta, end="", flush=True)
            accumulated = current_output
    return accumulated


def main():
    print("\nAgent 已准备就绪。输入 'exit' 退出。")
    chat_history = []
    while True:
        q = input("你: ").strip()
        if q.lower() == "exit":
            break
        force_route, query = _parse_mode(q)
        print("智能体:", end="", flush=True)
        final_text = asyncio.run(_stream_answer(query, chat_history, force_route))
        print()
        chat_history.extend([("human", query), ("ai", final_text)])


if __name__ == "__main__":
    main()

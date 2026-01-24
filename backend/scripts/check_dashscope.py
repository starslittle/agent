import os
import traceback
from pathlib import Path


def main() -> None:
    print("=== DashScope/ChatTongyi API 连通性自检 ===")
    # 优先加载 backend/.env
    try:
        from dotenv import load_dotenv
        backend_root = Path(__file__).resolve().parents[1]
        load_dotenv(backend_root / ".env")
    except Exception as e:
        print("[WARN] 加载 .env 失败:", e)

    key = os.getenv("DASHSCOPE_API_KEY", "")
    if not key:
        print("[FAIL] 未检测到环境变量 DASHSCOPE_API_KEY。请在 .env 或当前 shell 设置后重试。")
        return
    masked = key[:3] + "..." + key[-4:] if len(key) >= 8 else "(长度过短)"
    print(f"[OK] 检测到 DASHSCOPE_API_KEY = {masked}")

    try:
        from langchain_community.chat_models import ChatTongyi
        print("[STEP] 非流式调用测试…")
        llm = ChatTongyi(model="qwen-plus-2025-07-28", temperature=0.2, dashscope_api_key=key, streaming=False)
        resp = llm.invoke("用一句中文自我介绍")
        print("[OK] 非流式调用成功，返回:", getattr(resp, "content", str(resp))[:120].replace("\n", " "))
    except Exception as e:
        print("[ERR] 非流式调用失败:", e)
        traceback.print_exc()

    try:
        from langchain_community.chat_models import ChatTongyi
        print("[STEP] 流式调用测试…")
        llm2 = ChatTongyi(model="qwen-plus-2025-07-28", temperature=0.2, dashscope_api_key=key, streaming=True)
        got = False
        for i, chunk in enumerate(llm2.stream([("human", "请逐字回答: 你好世界")])):
            txt = getattr(chunk, "content", "")
            if txt and not got:
                print("[OK] 收到首个流式增量:", repr(txt))
                got = True
            if i > 30:
                break
        if not got:
            print("[ERR] 流式未收到任何增量（可能账号/模型无流式权限或网络受限）")
        else:
            print("[OK] 流式调用可用（截断打印）")
    except Exception as e:
        print("[ERR] 流式调用失败:", e)
        traceback.print_exc()

    print("=== 自检结束 ===")


if __name__ == "__main__":
    main()


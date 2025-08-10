import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 让脚本能从 src 导入 rag
ROOT = Path(__file__).resolve().parents[1]
src_path = ROOT / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from rag.system import RAGSystem, RAGConfig  # noqa: E402


def main():
    load_dotenv()
    cfg = RAGConfig()
    cfg.ENABLE_NOTION = True
    if os.getenv("NOTION_API_KEY"):
        cfg.NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    page_ids_csv = os.getenv("NOTION_PAGE_IDS", "")
    if page_ids_csv:
        cfg.NOTION_PAGE_IDS = [x.strip() for x in page_ids_csv.split(",") if x.strip()]
    db_id = os.getenv("NOTION_DATABASE_ID", "")
    if db_id:
        cfg.NOTION_DATABASE_ID = db_id
    rag = RAGSystem(cfg)
    rag.startup()
    qe = rag.get_query_engine("notion")
    if qe is None:
        print("初始化完成，但 Notion 引擎不可用（可能没有文档）。")
    else:
        print("Notion 引擎可用。")


if __name__ == "__main__":
    main()

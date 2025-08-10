import os
import json
import argparse
import requests
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", type=str, default="", help="关键词搜索，使用 Notion /v1/search")
    parser.add_argument("--id", dest="oid", type=str, default="", help="指定页面或数据库 ID（可无短横线）")
    args = parser.parse_args()

    load_dotenv()
    notion_key = os.getenv("NOTION_API_KEY", "")
    if not notion_key:
        print("ERROR: NOTION_API_KEY 未设置")
        return

    headers = {
        "Authorization": f"Bearer {notion_key}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    if args.query:
        r = requests.post("https://api.notion.com/v1/search", headers=headers, data=json.dumps({"query": args.query, "page_size": 10}), timeout=30)
        print(r.status_code, r.text)

    if args.oid:
        oid = args.oid
        if "-" not in oid and len(oid) == 32:
            oid = f"{oid[0:8]}-{oid[8:12]}-{oid[12:16]}-{oid[16:20]}-{oid[20:32]}"
        rp = requests.get(f"https://api.notion.com/v1/pages/{oid}", headers=headers, timeout=30)
        rd = requests.get(f"https://api.notion.com/v1/databases/{oid}", headers=headers, timeout=30)
        print("page:", rp.status_code)
        print("database:", rd.status_code)


if __name__ == "__main__":
    main()

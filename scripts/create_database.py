"""Notion に登録先のデータベースを作成する（初回に 1 回だけ実行する）。

使い方:
    python scripts/create_database.py <親ページの ID または URL>
    （NOTION_TOKEN は環境変数か .env で渡す）

親ページはあらかじめインテグレーションに共有しておく必要がある。
"""

from __future__ import annotations

import os
import re
import sys

from notion_client import Client

from claude_dev_watch.config import load_env
from claude_dev_watch.notion import DATABASE_PROPERTIES


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    load_env()
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        sys.exit("環境変数 NOTION_TOKEN が設定されていない")

    parent_id = _page_id(sys.argv[1])
    db = Client(auth=token).databases.create(
        parent={"type": "page_id", "page_id": parent_id},
        title=[{"type": "text", "text": {"content": "claude.dev ブログ（日本語訳）"}}],
        initial_data_source={"properties": DATABASE_PROPERTIES},
    )
    print(f"作成した: {db.get('url')}")
    print(f"NOTION_DATABASE_ID={db['id']}")
    return 0


def _page_id(value: str) -> str:
    # ページ URL の末尾にある 32 桁の ID を取り出す。ID をそのまま渡されたときにも対応する
    match = re.search(r"([0-9a-f]{32})(?:\?|$)", value.replace("-", ""))
    if not match:
        sys.exit(f"ページ ID を読み取れない: {value}")
    return match.group(1)


if __name__ == "__main__":
    sys.exit(main())

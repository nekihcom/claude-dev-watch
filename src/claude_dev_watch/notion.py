from __future__ import annotations

import logging
from datetime import datetime, timezone

from bs4 import BeautifulSoup, NavigableString, Tag
from notion_client import Client

from .article import (
    Block,
    Code,
    Heading,
    Image,
    ListBlock,
    Note,
    Paragraph,
    Quote,
    Table,
    Text,
    Video,
)
from .feed import Entry

log = logging.getLogger(__name__)

# Notion API の制約
MAX_TEXT_LENGTH = 2000  # rich_text 1 要素の content
MAX_RICH_TEXTS = 100  # 1 ブロックの rich_text 配列
MAX_CHILDREN = 100  # 1 リクエストで追加できる子ブロック

NOTION_LANGUAGES = {
    "javascript": "javascript",
    "typescript": "typescript",
    "python": "python",
    "json": "json",
    "shell": "shell",
    "bash": "bash",
    "sh": "shell",
    "yaml": "yaml",
    "html": "html",
    "css": "css",
    "go": "go",
    "rust": "rust",
    "sql": "sql",
    "markdown": "markdown",
}


# ---------- インライン HTML → rich_text ----------


def rich_text(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    segments: list[dict] = []
    _walk(soup, {"bold": False, "italic": False, "code": False}, None, segments)
    return _merge(segments)


def _walk(node: Tag, ann: dict, link: str | None, out: list[dict]) -> None:
    for child in node.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text:
                out.append({"text": text, "ann": dict(ann), "link": link})
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == "br":
            out.append({"text": "\n", "ann": dict(ann), "link": link})
            continue
        sub = dict(ann)
        sub_link = link
        if child.name in ("strong", "b"):
            sub["bold"] = True
        elif child.name in ("em", "i"):
            sub["italic"] = True
        elif child.name == "code":
            sub["code"] = True
        elif child.name == "a":
            href = child.get("href", "")
            # Notion は http(s) 以外のリンクを受け付けない
            if href.startswith(("http://", "https://")):
                sub_link = href
        _walk(child, sub, sub_link, out)


def _merge(segments: list[dict]) -> list[dict]:
    """書式が同じ隣接区間をまとめ、2,000 文字を超える区間は分割して Notion 形式にする。"""
    merged: list[dict] = []
    for seg in segments:
        if merged and merged[-1]["ann"] == seg["ann"] and merged[-1]["link"] == seg["link"]:
            merged[-1]["text"] += seg["text"]
        else:
            merged.append(dict(seg))

    result = []
    for seg in merged:
        for chunk in _split(seg["text"], MAX_TEXT_LENGTH):
            item = {
                "type": "text",
                "text": {"content": chunk, "link": {"url": seg["link"]} if seg["link"] else None},
                "annotations": seg["ann"],
            }
            result.append(item)
    return result


def _split(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def plain(text: str) -> list[dict]:
    return [{"type": "text", "text": {"content": c}} for c in _split(text, MAX_TEXT_LENGTH)]


# ---------- 中間表現 → Notion ブロック ----------


def to_blocks(blocks: list[Block]) -> list[dict]:
    out: list[dict] = []
    for b in blocks:
        out.extend(_block(b))
    return out


def _text_blocks(kind: str, text: Text, **extra) -> list[dict]:
    # rich_text が 100 要素を超えると API が拒否するため、同じ種類のブロックを続けて分割する
    rt = rich_text(text.html)
    chunks = [rt[i : i + MAX_RICH_TEXTS] for i in range(0, len(rt), MAX_RICH_TEXTS)] or [[]]
    return [{"type": kind, kind: {"rich_text": c, **extra}} for c in chunks]


def _block(b: Block) -> list[dict]:
    match b:
        case Heading(level=level, text=text):
            return _text_blocks(f"heading_{level}", text)
        case Paragraph(text=text):
            return _text_blocks("paragraph", text)
        case Quote(text=text):
            return _text_blocks("quote", text)
        case ListBlock():
            return _list(b)
        case Code(code=code, language=lang):
            chunks = plain(code)
            return [
                {
                    "type": "code",
                    "code": {
                        "rich_text": chunks[i : i + MAX_RICH_TEXTS],
                        "language": NOTION_LANGUAGES.get(lang.lower(), "plain text"),
                    },
                }
                for i in range(0, len(chunks), MAX_RICH_TEXTS)
            ]
        case Image(url=url, caption=caption):
            return [
                {
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {"url": url},
                        "caption": rich_text(caption.html)[:MAX_RICH_TEXTS] if caption else [],
                    },
                }
            ]
        case Video(url=url, caption=caption):
            # 任意の mp4 を Notion の video ブロックで埋め込めるとは限らないため、リンクとして置く
            html = f'▶ <a href="{url}">動画（原文サイト）</a>'
            if caption:
                html += " — " + caption.html
            return _text_blocks("paragraph", Text(html))
        case Note(label=label, caption=caption):
            parts = [p for p in (label.html, caption.html if caption else "") if p]
            html = "図（原文を参照）" + ("：" + " — ".join(parts) if parts else "")
            return _text_blocks("callout", Text(html), icon={"type": "emoji", "emoji": "🖼️"})
        case Table(rows=rows, has_header=has_header):
            if not rows:
                return []
            width = max(len(r) for r in rows)
            children = [
                {
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            rich_text(r[i].html)[:MAX_RICH_TEXTS] if i < len(r) else [] for i in range(width)
                        ]
                    },
                }
                for r in rows
            ]
            return [
                {
                    "type": "table",
                    "table": {
                        "table_width": width,
                        "has_column_header": has_header,
                        "has_row_header": False,
                        "children": children,
                    },
                }
            ]
    raise TypeError(f"未対応のブロック: {b!r}")


def _list(b: ListBlock) -> list[dict]:
    kind = "numbered_list_item" if b.ordered else "bulleted_list_item"
    out = []
    for item in b.items:
        blocks = _text_blocks(kind, item.text)
        if item.children:
            blocks[-1][kind]["children"] = [c for sub in item.children for c in _list(sub)]
        out.extend(blocks)
    return out


# ---------- Notion API ----------


class NotionStore:
    def __init__(self, token: str, database_id: str) -> None:
        self._client = Client(auth=token)
        db = self._client.databases.retrieve(database_id=database_id)
        sources = db.get("data_sources") or []
        if not sources:
            raise RuntimeError("データベースにデータソースがない")
        # Notion API 2025-09-03 以降、ページの照会と作成はデータベースではなくデータソースに対して行う
        self._data_source_id = sources[0]["id"]

    def existing_urls(self) -> set[str]:
        urls: set[str] = set()
        cursor = None
        while True:
            kwargs = {"page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            res = self._client.data_sources.query(self._data_source_id, **kwargs)
            for page in res["results"]:
                url = page.get("properties", {}).get("URL", {}).get("url")
                if url:
                    urls.add(url)
            if not res.get("has_more"):
                return urls
            cursor = res["next_cursor"]

    def create_page(self, entry: Entry, title_ja: str, summary_ja: str, blocks: list[dict]) -> str:
        children = [_source_callout(entry.url)] + blocks
        page = self._client.pages.create(
            parent={"type": "data_source_id", "data_source_id": self._data_source_id},
            properties=_properties(entry, title_ja, summary_ja),
            children=children[:MAX_CHILDREN],
        )
        page_id = page["id"]
        try:
            for i in range(MAX_CHILDREN, len(children), MAX_CHILDREN):
                self._client.blocks.children.append(page_id, children=children[i : i + MAX_CHILDREN])
        except Exception:
            # 本文が途中までのページが残ると、URL による重複判定で以後ずっと再登録されなくなる。
            # ゴミ箱に移して次回の実行で作り直させる
            log.error("本文の追加に失敗したため、作成途中のページをゴミ箱に移す: %s", page_id)
            self._client.pages.update(page_id, in_trash=True)
            raise
        return page.get("url", page_id)


def _source_callout(url: str) -> dict:
    return {
        "type": "callout",
        "callout": {
            "rich_text": [
                {"type": "text", "text": {"content": "原文："}},
                {"type": "text", "text": {"content": url, "link": {"url": url}}},
            ],
            "icon": {"type": "emoji", "emoji": "🔗"},
        },
    }


def _properties(entry: Entry, title_ja: str, summary_ja: str) -> dict:
    props: dict = {
        "タイトル": {"title": plain(title_ja)},
        "原題": {"rich_text": plain(entry.title)},
        "URL": {"url": entry.url},
        "著者": {"rich_text": plain(entry.author)},
        "要約": {"rich_text": plain(summary_ja)},
        "登録日時": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }
    if entry.published:
        props["公開日"] = {"date": {"start": entry.published.date().isoformat()}}
    if entry.category:
        # select は未登録の選択肢名を渡すと Notion 側で自動的に追加される
        props["カテゴリ"] = {"select": {"name": entry.category}}
    return props


DATABASE_PROPERTIES = {
    "タイトル": {"title": {}},
    "原題": {"rich_text": {}},
    "URL": {"url": {}},
    "公開日": {"date": {}},
    "著者": {"rich_text": {}},
    "カテゴリ": {"select": {}},
    "要約": {"rich_text": {}},
    "登録日時": {"date": {}},
}

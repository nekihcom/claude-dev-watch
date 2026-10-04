"""翻訳した記事を 1 記事 1 ファイルの JSON として保存する。

HTML ではなく中間表現を残すのは、ページのデザインを変えたときに DeepL で翻訳し直さずにサイト全体を作り直すため。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .article import Block, Code, Heading, Image, ListBlock, ListItem, Note, Paragraph, Quote, Table, Text, Video
from .feed import Entry


@dataclass
class StoredArticle:
    entry: Entry
    title_ja: str
    summary_ja: str
    blocks: list[Block]
    translated_at: datetime

    @property
    def slug(self) -> str:
        return slug_of(self.entry.url)


def slug_of(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


class ContentStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def existing_urls(self) -> set[str]:
        return {a.entry.url for a in self.load_all()}

    def save(self, entry: Entry, title_ja: str, summary_ja: str, blocks: list[Block]) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        article = StoredArticle(entry, title_ja, summary_ja, blocks, datetime.now(timezone.utc))
        path = self._root / f"{article.slug}.json"
        # 一時ファイル経由で置き換えるのは、書き込み途中で落ちたときに壊れた JSON を残さないため
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_dump_article(article), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def load_all(self) -> list[StoredArticle]:
        if not self._root.is_dir():
            return []
        return [_load_article(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(self._root.glob("*.json"))]


def _dump_article(a: StoredArticle) -> dict:
    e = a.entry
    return {
        "url": e.url,
        "title": e.title,
        "title_ja": a.title_ja,
        "published": e.published.isoformat() if e.published else None,
        "author": e.author,
        "category": e.category,
        "summary": e.summary,
        "summary_ja": a.summary_ja,
        "translated_at": a.translated_at.isoformat(),
        "blocks": [_dump_block(b) for b in a.blocks],
    }


def _load_article(d: dict) -> StoredArticle:
    entry = Entry(
        title=d["title"],
        url=d["url"],
        published=datetime.fromisoformat(d["published"]) if d["published"] else None,
        author=d["author"],
        category=d["category"],
        summary=d["summary"],
    )
    return StoredArticle(
        entry=entry,
        title_ja=d["title_ja"],
        summary_ja=d["summary_ja"],
        blocks=[_load_block(b) for b in d["blocks"]],
        translated_at=datetime.fromisoformat(d["translated_at"]),
    )


def _text(t: Text | None) -> str | None:
    return None if t is None else t.html


def _dump_block(b: Block) -> dict:
    match b:
        case Heading(level=level, text=t):
            return {"type": "heading", "level": level, "text": t.html}
        case Paragraph(text=t):
            return {"type": "paragraph", "text": t.html}
        case Quote(text=t):
            return {"type": "quote", "text": t.html}
        case ListBlock(ordered=ordered, items=items):
            return {
                "type": "list",
                "ordered": ordered,
                "items": [{"text": i.text.html, "children": [_dump_block(c) for c in i.children]} for i in items],
            }
        case Code(code=code, language=lang):
            return {"type": "code", "code": code, "language": lang}
        case Image(url=url, caption=c):
            return {"type": "image", "url": url, "caption": _text(c)}
        case Video(url=url, caption=c):
            return {"type": "video", "url": url, "caption": _text(c)}
        case Table(rows=rows, has_header=has_header):
            return {"type": "table", "has_header": has_header, "rows": [[c.html for c in r] for r in rows]}
        case Note(label=label, caption=c):
            return {"type": "note", "label": label.html, "caption": _text(c)}
    raise TypeError(f"未対応のブロック: {b!r}")


def _opt(html: str | None) -> Text | None:
    return None if html is None else Text(html)


def _load_block(d: dict) -> Block:
    match d["type"]:
        case "heading":
            return Heading(d["level"], Text(d["text"]))
        case "paragraph":
            return Paragraph(Text(d["text"]))
        case "quote":
            return Quote(Text(d["text"]))
        case "list":
            items = [ListItem(Text(i["text"]), [_load_block(c) for c in i["children"]]) for i in d["items"]]
            return ListBlock(d["ordered"], items)
        case "code":
            return Code(d["code"], d["language"])
        case "image":
            return Image(d["url"], _opt(d["caption"]))
        case "video":
            return Video(d["url"], _opt(d["caption"]))
        case "table":
            return Table([[Text(c) for c in r] for r in d["rows"]], d["has_header"])
        case "note":
            return Note(Text(d["label"]), _opt(d["caption"]))
    raise ValueError(f"未対応のブロック種別: {d['type']}")

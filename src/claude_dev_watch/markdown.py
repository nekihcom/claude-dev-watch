"""--dry-run 用に、中間表現を Markdown にする。Notion に書き込まずに訳文と構造を確認するため。"""

from __future__ import annotations

from bs4 import BeautifulSoup, NavigableString, Tag

from .article import Block, Code, Heading, Image, ListBlock, Note, Paragraph, Quote, Table, Video
from .feed import Entry


def render(entry: Entry, title_ja: str, summary_ja: str, blocks: list[Block]) -> str:
    lines = [
        f"# {title_ja}",
        "",
        f"- 原題：{entry.title}",
        f"- 原文：{entry.url}",
        f"- 公開日：{entry.published.date().isoformat() if entry.published else ''}",
        f"- 著者：{entry.author}",
        f"- カテゴリ：{entry.category}",
        f"- 要約：{inline(summary_ja)}",
        "",
    ]
    for b in blocks:
        lines.extend(_block(b))
        lines.append("")
    return "\n".join(lines)


def _block(b: Block) -> list[str]:
    match b:
        case Heading(level=level, text=t):
            return [f"{'#' * (level + 1)} {inline(t.html)}"]
        case Paragraph(text=t):
            return [inline(t.html)]
        case Quote(text=t):
            return [f"> {inline(t.html)}"]
        case ListBlock():
            return _list(b, 0)
        case Code(code=code, language=lang):
            return [f"```{lang.lower()}", code, "```"]
        case Image(url=url, caption=c):
            return [f"![{inline(c.html) if c else ''}]({url})"]
        case Video(url=url, caption=c):
            return [f"▶ [動画（原文サイト）]({url}) {inline(c.html) if c else ''}"]
        case Note(label=label, caption=c):
            parts = [inline(x.html) for x in (label, c) if x and x.html]
            return [f"> 🖼️ 図（原文を参照）{'：' + ' — '.join(parts) if parts else ''}"]
        case Table(rows=rows, has_header=has_header):
            if not rows:
                return []
            width = max(len(r) for r in rows)
            md = [_row([inline(c.html) for c in r], width) for r in rows]
            sep = "|" + "---|" * width
            return [md[0], sep, *md[1:]] if has_header else [_row([""] * width, width), sep, *md]
    return []


def _row(cells: list[str], width: int) -> str:
    cells = cells + [""] * (width - len(cells))
    return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"


def _list(b: ListBlock, depth: int) -> list[str]:
    out = []
    for n, item in enumerate(b.items, 1):
        mark = f"{n}." if b.ordered else "-"
        out.append(f"{'  ' * depth}{mark} {inline(item.text.html)}")
        for sub in item.children:
            out.extend(_list(sub, depth + 1))
    return out


def inline(html: str) -> str:
    return _walk(BeautifulSoup(html, "html.parser")).strip()


def _walk(node: Tag) -> str:
    out = []
    for child in node.children:
        if isinstance(child, NavigableString):
            out.append(str(child))
        elif isinstance(child, Tag):
            inner = _walk(child)
            if child.name == "br":
                out.append("  \n")
            elif child.name in ("strong", "b"):
                out.append(f"**{inner}**")
            elif child.name in ("em", "i"):
                out.append(f"*{inner}*")
            elif child.name == "code":
                out.append(f"`{inner}`")
            elif child.name == "a" and child.get("href"):
                out.append(f"[{inner}]({child['href']})")
            else:
                out.append(inner)
    return "".join(out)

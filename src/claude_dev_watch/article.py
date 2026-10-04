"""記事ページの HTML から本文を取り出し、HTML にも Markdown にも変換できる中間表現にする。

サイトの HTML 構造に依存する処理はこのモジュールに閉じ込める。構造が変わったときの修正範囲を絞るため。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from . import USER_AGENT

log = logging.getLogger(__name__)

# 翻訳と出力で扱えるインライン要素だけを残す。それ以外のタグは中身のテキストだけにする
INLINE_TAGS = {"a", "code", "strong", "b", "em", "i", "br"}


@dataclass
class Text:
    """翻訳対象のインライン HTML。翻訳処理が html を訳文に置き換える。"""

    html: str


@dataclass
class Heading:
    level: int
    text: Text


@dataclass
class Paragraph:
    text: Text


@dataclass
class ListItem:
    text: Text
    children: list[ListBlock] = field(default_factory=list)


@dataclass
class ListBlock:
    ordered: bool
    items: list[ListItem]


@dataclass
class Code:
    code: str
    language: str


@dataclass
class Quote:
    text: Text


@dataclass
class Image:
    url: str
    caption: Text | None


@dataclass
class Video:
    url: str
    caption: Text | None


@dataclass
class Table:
    rows: list[list[Text]]
    has_header: bool


@dataclass
class Note:
    """再現できない図（SVG・インタラクティブな可視化など）の代わりに置く注記。原文の参照を促す。"""

    label: Text
    caption: Text | None


Block = Heading | Paragraph | ListBlock | Code | Quote | Image | Video | Table | Note


class ArticleParseError(Exception):
    pass


def fetch_html(url: str) -> str:
    res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    res.raise_for_status()
    # Content-Type に charset がなく requests が ISO-8859-1 と誤判定するため、UTF-8 として明示的に解釈する
    return res.content.decode("utf-8")


def parse_article(html: str, base_url: str) -> list[Block]:
    soup = BeautifulSoup(html, "html.parser")
    body = soup.select_one("div#body")
    if body is None:
        raise ArticleParseError("本文（div#body）が見つからない。サイトの HTML 構造が変わった可能性がある")

    sections = body.find_all("section", recursive=False) or [body]
    blocks: list[Block] = []
    for section in sections:
        for el in section.children:
            if isinstance(el, Tag):
                blocks.extend(_convert(el, base_url))
    if not blocks:
        raise ArticleParseError("本文からブロックを 1 件も取り出せなかった")
    return blocks


def _convert(el: Tag, base: str) -> list[Block]:
    classes = set(el.get("class") or [])
    name = el.name

    if name in ("h2", "h3", "h4"):
        return [Heading(min(int(name[1]) - 1, 3), _inline(el, base))]
    if name == "p":
        text = _inline(el, base)
        return [Paragraph(text)] if text.html.strip() else []
    if name in ("ul", "ol"):
        return [_list(el, base)]
    if name == "blockquote":
        return _quotes(el, base)
    if name == "div" and "art-code" in classes:
        return [_code(el)]
    if name == "div" and "art-table" in classes:
        table = el.find("table")
        return [_table(table, base)] if table else []
    if name == "figure":
        return _figure(el, base, classes)
    if name in ("style", "script"):
        return []

    log.warning("未対応の要素を段落として扱う: <%s class=%s>", name, " ".join(classes))
    text = el.get_text(" ", strip=True)
    return [Paragraph(Text(_escape(text)))] if text else []


def _list(el: Tag, base: str) -> ListBlock:
    items = []
    for li in el.find_all("li", recursive=False):
        nested = [_list(sub, base) for sub in li.find_all(["ul", "ol"], recursive=False)]
        for sub in li.find_all(["ul", "ol"], recursive=False):
            sub.extract()
        items.append(ListItem(_inline(li, base), nested))
    return ListBlock(ordered=el.name == "ol", items=items)


def _quotes(el: Tag, base: str) -> list[Block]:
    paragraphs = el.find_all("p")
    if not paragraphs:
        return [Quote(_inline(el, base))]
    return [Quote(_inline(p, base)) for p in paragraphs]


def _code(el: Tag) -> Code:
    pre = el.find("pre")
    code = pre.get_text() if pre else ""
    lang_el = el.select_one("div.ch .lang")
    language = lang_el.get_text(strip=True) if lang_el else "Text"
    return Code(code=code.rstrip("\n"), language=language)


def _table(table: Tag, base: str) -> Table:
    rows = []
    for tr in table.find_all("tr"):
        rows.append([_inline(cell, base) for cell in tr.find_all(["th", "td"], recursive=False)])
    has_header = table.find("thead") is not None
    return Table(rows=rows, has_header=has_header)


def _figure(el: Tag, base: str, classes: set[str]) -> list[Block]:
    caption = _caption(el, base)

    if "art-video" in classes:
        video = el.find("video", src=True)
        if video:
            return [Video(urljoin(base, video["src"]), caption)]

    if "art-thread" in classes:
        # チャットのスレッドを再現した図。発言者と本文を引用として並べる
        blocks: list[Block] = []
        for msg in el.select("li.msg"):
            who = msg.select_one(".mh b")
            body = msg.select_one(".mx")
            if body is None:
                continue
            prefix = f"<strong>{_escape(who.get_text(strip=True))}</strong>: " if who else ""
            for p in body.find_all("p") or [body]:
                blocks.append(Quote(Text(prefix + _inline(p, base).html)))
                prefix = ""
        if caption:
            blocks.append(Paragraph(caption))
        return blocks

    if "art-xpost" in classes:
        blocks = [Quote(_inline(p, base)) for p in el.select(".xp-text p")]
        link = el.select_one(".xp-f a[href]")
        if link:
            href = urljoin(base, link["href"])
            blocks.append(Paragraph(Text(f'<a href="{_escape(href)}">View on X</a>')))
        return blocks

    if "art-diagram" in classes or "viz" in classes or el.find("svg"):
        title = el.select_one(".fig-title")
        label = _inline(title, base) if title else Text("")
        return [Note(label=label, caption=caption)]

    img = el.find("img", src=True)
    if img:
        return [Image(urljoin(base, img["src"]), caption)]

    log.warning("未対応の図を注記として扱う: class=%s", " ".join(classes))
    return [Note(label=Text(""), caption=caption)]


def _caption(el: Tag, base: str) -> Text | None:
    cap = el.find("figcaption")
    if cap is None:
        return None
    for btn in cap.find_all("button"):
        btn.decompose()
    # 「FIG A」ラベルと説明文が別要素で隣接しており、そのままだと語がつながってしまう
    for label in cap.find_all("b", recursive=False):
        label.insert_after(" ")
    text = _inline(cap, base)
    return text if text.html.strip() else None


def _inline(el: Tag, base: str) -> Text:
    """要素の中身を、許可したインラインタグだけを含む HTML 文字列にする。"""
    return Text(_inline_html(el, base).strip())


def _inline_html(el: Tag, base: str) -> str:
    out = []
    for node in el.children:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            out.append(_escape(str(node)))
            continue
        if not isinstance(node, Tag) or node.name in ("button", "svg", "script", "style"):
            continue
        inner = _inline_html(node, base)
        if node.name == "br":
            out.append("<br>")
        elif node.name == "a" and node.get("href"):
            href = urljoin(base, node["href"])
            out.append(f'<a href="{_escape(href)}">{inner}</a>')
        elif node.name in INLINE_TAGS - {"a", "br"}:
            out.append(f"<{node.name}>{inner}</{node.name}>")
        else:
            out.append(inner)
    return "".join(out)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def iter_texts(blocks: list[Block]):
    """翻訳対象の Text を文書順に列挙する。"""
    for b in blocks:
        match b:
            case Heading(text=t) | Paragraph(text=t) | Quote(text=t):
                yield t
            case ListBlock(items=items):
                for item in items:
                    yield item.text
                    yield from iter_texts(item.children)
            case Note(label=label, caption=c):
                if label.html:
                    yield label
                if c is not None:
                    yield c
            case Image(caption=c) | Video(caption=c):
                if c is not None:
                    yield c
            case Table(rows=rows):
                for row in rows:
                    yield from row

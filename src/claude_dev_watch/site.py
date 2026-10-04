"""保存した翻訳記事（content/*.json）から GitHub Pages 用の静的サイトを生成する。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from .article import Block, Code, Diagram, Heading, Image, ListBlock, Note, Paragraph, Quote, Table, Text, Video
from .store import ContentStore, StoredArticle
from .svg import sanitize_svg

log = logging.getLogger(__name__)

SITE_TITLE = "claude.dev 日本語訳"
SOURCE_BLOG = "https://claude.dev/blog"

# 訳文は DeepL を経由しており、公開ページにそのまま埋め込むと想定外のタグが混ざりうる。出力時にも許可したタグだけに絞る
_ALLOWED_TAGS = {"a", "code", "strong", "b", "em", "i", "br"}
_ALLOWED_SCHEMES = {"http", "https", "mailto"}
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def build(content: Path, out: Path) -> int:
    articles = ContentStore(content).load_all()
    articles.sort(key=lambda a: a.entry.published or _EPOCH, reverse=True)

    # 出力先は消さずに上書きする。--site-out の指定を誤ってもリポジトリ内のファイルを消さないため
    (out / "articles").mkdir(parents=True, exist_ok=True)
    (out / "style.css").write_text(CSS, encoding="utf-8")
    (out / "index.html").write_text(render_index(articles), encoding="utf-8")
    for a in articles:
        (out / "articles" / f"{a.slug}.html").write_text(render_article(a), encoding="utf-8")
    log.info("サイトを生成した: %s（%d 記事）", out, len(articles))
    return len(articles)


def render_index(articles: list[StoredArticle]) -> str:
    items = "\n".join(_index_item(a) for a in articles) or '<p class="empty">まだ記事がない。</p>'
    body = f"""<header class="site-header">
  <h1>{escape(SITE_TITLE)}</h1>
  <p class="lead"><a href="{SOURCE_BLOG}">claude.dev ブログ</a>の記事を DeepL で機械翻訳した非公式の日本語訳。正確な内容は各記事の原文を参照のこと。</p>
</header>
<main>
<ol class="article-list">
{items}
</ol>
</main>"""
    return _page(SITE_TITLE, body, css="style.css")


def _index_item(a: StoredArticle) -> str:
    e = a.entry
    return f"""<li>
  <article>
    <p class="meta">{_meta_line(a)}</p>
    <h2><a href="articles/{escape(a.slug)}.html">{escape(a.title_ja)}</a></h2>
    <p class="original-title" lang="en">{escape(e.title)}</p>
    <p class="summary">{escape(a.summary_ja)}</p>
  </article>
</li>"""


def render_article(a: StoredArticle) -> str:
    e = a.entry
    content = "\n".join(_block(b, e.url) for b in a.blocks)
    body = f"""<header class="site-header compact">
  <a class="back" href="../index.html">← {escape(SITE_TITLE)}</a>
</header>
<main>
<article>
  <header class="article-header">
    <p class="meta">{_meta_line(a)}</p>
    <h1>{escape(a.title_ja)}</h1>
    <p class="original-title" lang="en">{escape(e.title)}</p>
    <p class="byline">{escape(e.author)}</p>
    <p class="notice">この記事は <a href="{_url(e.url)}">原文</a> を DeepL で機械翻訳したものである。正確な内容は原文を参照のこと。</p>
  </header>
  <div class="prose">
{content}
  </div>
</article>
</main>"""
    return _page(f"{a.title_ja} | {SITE_TITLE}", body, css="../style.css", description=a.summary_ja)


def _meta_line(a: StoredArticle) -> str:
    e = a.entry
    parts = []
    if e.published:
        parts.append(f'<time datetime="{e.published.date().isoformat()}">{e.published.date().isoformat()}</time>')
    if e.category:
        parts.append(f'<span class="category">{escape(e.category)}</span>')
    return " · ".join(parts)


def _page(title: str, body: str, css: str, description: str = "") -> str:
    desc = f'\n<meta name="description" content="{escape(description)}">' if description else ""
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>{desc}
<link rel="stylesheet" href="{css}">
</head>
<body>
{body}
<footer class="site-footer">
  <p>非公式の機械翻訳。原文の著作権は各著者および Anthropic に帰属する。</p>
</footer>
</body>
</html>
"""


def _block(b: Block, source_url: str) -> str:
    match b:
        case Heading(level=level, text=t):
            tag = f"h{level + 1}"
            return f"<{tag}>{inline(t.html)}</{tag}>"
        case Paragraph(text=t):
            return f"<p>{inline(t.html)}</p>"
        case Quote(text=t):
            return f"<blockquote><p>{inline(t.html)}</p></blockquote>"
        case ListBlock():
            return _list(b)
        case Code(code=code, language=lang):
            return (
                f'<figure class="code"><figcaption>{escape(lang)}</figcaption>'
                f"<pre><code>{escape(code)}</code></pre></figure>"
            )
        case Image(url=url, caption=c):
            alt = _plain(c)
            return (
                f'<figure><img src="{_url(url)}" alt="{escape(alt)}" loading="lazy" decoding="async">'
                f"{_caption(c)}</figure>"
            )
        case Video(url=url, caption=c):
            return f'<figure><video src="{_url(url)}" controls preload="none"></video>{_caption(c)}</figure>'
        case Diagram(label=label, caption=c, svgs=svgs, description=desc):
            # 保存済みの JSON は手で編集されうるため、取り込み時に加えて出力時にも無害化する
            draw = "".join(sanitize_svg(svg) for svg in svgs)
            title = f'<div class="diagram-title">{inline(label.html)}</div>' if label.html else ""
            return (
                f'<figure class="diagram">{title}'
                f'<div class="diagram-draw" role="img" aria-label="{escape(desc or _plain(label))}">{draw}</div>'
                f"{_caption(c)}</figure>"
            )
        case Note(label=label, caption=c):
            parts = [inline(x.html) for x in (label, c) if x and x.html]
            detail = f"：{' — '.join(parts)}" if parts else ""
            return f'<aside class="note">図は <a href="{_url(source_url)}">原文</a> を参照{detail}</aside>'
        case Table(rows=rows, has_header=has_header):
            return _table(rows, has_header)
    return ""


def _caption(c: Text | None) -> str:
    return f"<figcaption>{inline(c.html)}</figcaption>" if c and c.html else ""


def _list(b: ListBlock) -> str:
    tag = "ol" if b.ordered else "ul"
    items = []
    for item in b.items:
        children = "".join(_list(c) for c in item.children)
        items.append(f"<li>{inline(item.text.html)}{children}</li>")
    return f"<{tag}>{''.join(items)}</{tag}>"


def _table(rows: list[list[Text]], has_header: bool) -> str:
    if not rows:
        return ""

    def row(cells: list[Text], cell: str) -> str:
        return "<tr>" + "".join(f"<{cell}>{inline(c.html)}</{cell}>" for c in cells) + "</tr>"

    head, body = (rows[0], rows[1:]) if has_header else (None, rows)
    thead = f"<thead>{row(head, 'th')}</thead>" if head else ""
    tbody = "<tbody>" + "".join(row(r, "td") for r in body) + "</tbody>"
    return f'<div class="table-wrap"><table>{thead}{tbody}</table></div>'


def inline(html: str) -> str:
    """インライン HTML を、許可したタグと安全なリンクだけを含む形に作り直す。"""
    return _walk(BeautifulSoup(html, "html.parser"))


def _walk(node: Tag) -> str:
    out = []
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            out.append(escape(str(child), quote=False))
        elif isinstance(child, Tag):
            if child.name in ("script", "style"):
                continue
            inner = _walk(child)
            if child.name not in _ALLOWED_TAGS:
                out.append(inner)
            elif child.name == "br":
                out.append("<br>")
            elif child.name == "a":
                href = child.get("href")
                out.append(f'<a href="{_url(href)}">{inner}</a>' if href and _safe(href) else inner)
            else:
                out.append(f"<{child.name}>{inner}</{child.name}>")
    return "".join(out)


def _plain(t: Text | None) -> str:
    return BeautifulSoup(t.html, "html.parser").get_text() if t else ""


def _safe(url: str) -> bool:
    return urlparse(url.strip()).scheme.lower() in _ALLOWED_SCHEMES


def _url(url: str) -> str:
    # javascript: などのスキームを属性に出さないため、許可外の URL は無効なリンクにする
    return escape(url.strip()) if _safe(url) else "#"


CSS = """:root {
  --bg: #fbfaf7;
  --surface: #ffffff;
  --text: #1f1e1c;
  --muted: #6b6862;
  --border: #e4e1da;
  --accent: #b6532f;
  --code-bg: #f3f1ec;
  --note-bg: #f6f1e7;
  color-scheme: light dark;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1918;
    --surface: #222120;
    --text: #e9e6e0;
    --muted: #a19d95;
    --border: #3a3835;
    --accent: #e48a63;
    --code-bg: #2a2826;
    --note-bg: #2c2925;
  }
}
/* 図の SVG は原文サイトの CSS 変数で色を指定している。値は claude.dev の CSS から写した。
   サイト側の変数と名前が衝突しないよう、図の中だけで定義する。--bg はサイトの背景色をそのまま使う */
.diagram {
  --ink: #141413;
  --ink-2: #4c4b45;
  --line: #14141338;
  --line-soft: #1414131c;
  --bg-raised: #f1efe8;
  --bg-panel: #ece9e0;
  --fig-focal: var(--accent);
  --viz-muted: #65645e;
  --viz-wash: var(--bg-raised);
  --viz-wash-2: var(--bg-panel);
  --viz-b0: #788c5d;
  --viz-b1: #b57da8;
  --viz-b2: #955488;
  --viz-b3: #763269;
  --viz-b4: #501a47;
  --viz-b5: #728eb7;
  --viz-b6: #4f70a0;
  --viz-b7: #31507e;
  --viz-b8: #183053;
  --viz-b9: #8e8c87;
  --viz-m1: #3d3d3a;
  --viz-g0: #b46d4f;
  --viz-g1: #7a7973;
  --viz-g2: #86847e;
  --viz-g3: #9a9892;
  --fig-series-1: var(--viz-m1);
  --fig-series-2: var(--viz-muted);
  --fig-series-3: var(--viz-b9);
  --fig-dash-1: none;
  --fig-dash-2: 5 3;
  --fig-dash-3: 1.5 3;
  --fig-chart-ink: var(--viz-muted);
}
@media (prefers-color-scheme: dark) {
  .diagram {
    --ink: #faf9f5;
    --ink-2: #b0aea5;
    --line: #faf9f529;
    --line-soft: #faf9f517;
    --bg-raised: #1a1a18;
    --bg-panel: #1e1d1b;
    --viz-muted: #8f8e87;
    --viz-wash: #1c1c1a;
    --viz-wash-2: #20201e;
    --viz-b1: #925786;
    --viz-b2: #b776a9;
    --viz-b3: #d59cc8;
    --viz-b4: #f2c3e7;
    --viz-b5: #51709d;
    --viz-b6: #7191c0;
    --viz-b7: #98b3db;
    --viz-b8: #c2d6f2;
    --viz-b9: #73716c;
    --viz-m1: #d1cfc5;
    --viz-g0: #9a5b44;
    --viz-g1: #8a8983;
    --viz-g2: #6f6e69;
    --viz-g3: #5a5955;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: system-ui, -apple-system, "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Yu Gothic UI", Meiryo, sans-serif;
  font-size: 17px;
  line-height: 1.85;
  overflow-wrap: anywhere;
}
a { color: var(--accent); text-underline-offset: 0.2em; }
.site-header, main, .site-footer { max-width: 46rem; margin: 0 auto; padding: 0 16px; }
.site-header { padding-top: 3rem; padding-bottom: 1.5rem; }
.site-header.compact { padding-top: 1.5rem; padding-bottom: 0; }
.site-header h1 { font-size: 1.75rem; line-height: 1.4; margin: 0 0 0.5rem; }
.lead { color: var(--muted); margin: 0; font-size: 0.95rem; }
.back { font-size: 0.9rem; text-decoration: none; }
.meta { color: var(--muted); font-size: 0.85rem; margin: 0; letter-spacing: 0.02em; }
.category { text-transform: uppercase; }
.original-title { color: var(--muted); font-size: 0.9rem; margin: 0.25rem 0 0; line-height: 1.5; }

.article-list { list-style: none; margin: 0; padding: 0; }
.article-list li { border-top: 1px solid var(--border); padding: 1.5rem 0; }
.article-list h2 { font-size: 1.25rem; line-height: 1.5; margin: 0.25rem 0 0; }
.article-list h2 a { color: var(--text); text-decoration: none; }
.article-list h2 a:hover { color: var(--accent); }
.summary { margin: 0.75rem 0 0; font-size: 0.95rem; }
.empty { color: var(--muted); }

.article-header { padding: 2rem 0 1.5rem; border-bottom: 1px solid var(--border); margin-bottom: 2rem; }
.article-header h1 { font-size: 1.9rem; line-height: 1.45; margin: 0.4rem 0 0; }
.byline { margin: 0.75rem 0 0; font-size: 0.9rem; }
.notice { margin: 1.25rem 0 0; padding: 0.75rem 1rem; background: var(--note-bg); border-radius: 6px; font-size: 0.85rem; color: var(--muted); }

.prose h2 { font-size: 1.45rem; line-height: 1.5; margin: 2.75rem 0 1rem; }
.prose h3 { font-size: 1.2rem; line-height: 1.5; margin: 2.25rem 0 0.75rem; }
.prose h4 { font-size: 1.05rem; line-height: 1.5; margin: 2rem 0 0.5rem; }
.prose p, .prose ul, .prose ol { margin: 0 0 1.25rem; }
.prose li { margin: 0.25rem 0; }
.prose li > ul, .prose li > ol { margin: 0.25rem 0 0; }
.prose blockquote { margin: 0 0 1.25rem; padding: 0.1rem 0 0.1rem 1rem; border-left: 3px solid var(--border); color: var(--muted); }
.prose blockquote p { margin: 0; }
.prose :not(pre) > code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.88em; background: var(--code-bg); padding: 0.1em 0.35em; border-radius: 4px; }
.prose figure { margin: 1.75rem 0; }
.prose img, .prose video { display: block; max-width: 100%; height: auto; border-radius: 6px; background: var(--code-bg); }
.prose figcaption { color: var(--muted); font-size: 0.85rem; line-height: 1.6; margin-top: 0.5rem; }
.prose figure.code { background: var(--code-bg); border-radius: 6px; overflow: hidden; }
.prose figure.code figcaption { margin: 0; padding: 0.4rem 1rem; font-size: 0.75rem; border-bottom: 1px solid var(--border); }
.prose pre { margin: 0; padding: 1rem; overflow-x: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; line-height: 1.6; overflow-wrap: normal; }
.prose figure.diagram { padding: 1rem; border: 1px solid var(--border); border-radius: 6px; }
.diagram-title { font-weight: 600; font-size: 0.95rem; line-height: 1.5; margin-bottom: 0.75rem; }
.diagram-draw svg { display: block; width: 100%; height: auto; }
/* 原文は画面幅に応じて描き分けた 2 枚の SVG を持ち、CSS で片方だけを表示している */
.diagram-draw .art-diagram-narrow { display: none; }
@media (max-width: 640px) {
  .diagram-draw .art-diagram-wide { display: none; }
  .diagram-draw .art-diagram-narrow { display: block; max-width: 420px; margin-inline: auto; }
}
.prose .note { margin: 1.75rem 0; padding: 0.75rem 1rem; background: var(--note-bg); border-radius: 6px; font-size: 0.9rem; color: var(--muted); }
.table-wrap { overflow-x: auto; margin: 0 0 1.5rem; }
.prose table { border-collapse: collapse; font-size: 0.9rem; line-height: 1.6; min-width: 100%; }
.prose th, .prose td { border: 1px solid var(--border); padding: 0.5rem 0.75rem; text-align: left; vertical-align: top; }
.prose th { background: var(--code-bg); }

.site-footer { padding-top: 3rem; padding-bottom: 3rem; color: var(--muted); font-size: 0.8rem; }
"""

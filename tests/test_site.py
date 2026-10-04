from datetime import datetime, timezone

from claude_dev_watch.article import Code, Diagram, Image, Note, Paragraph, Text
from claude_dev_watch.feed import Entry
from claude_dev_watch.site import build, inline, render_article
from claude_dev_watch.store import ContentStore, StoredArticle


def _entry(n: int, published=True) -> Entry:
    return Entry(
        title=f"Title {n}",
        url=f"https://claude.dev/blog/post-{n}/",
        published=datetime(2026, 10, n, tzinfo=timezone.utc) if published else None,
        author="Author",
        category="Tutorials",
        summary="Summary",
    )


def test_index_lists_newest_first(tmp_path):
    store = ContentStore(tmp_path / "content")
    for n in (1, 3, 2):
        store.save(_entry(n), f"記事{n}", "要約", [])
    store.save(_entry(4, published=False), "日付なし", "要約", [])

    assert build(tmp_path / "content", tmp_path / "site") == 4
    index = (tmp_path / "site" / "index.html").read_text(encoding="utf-8")
    positions = [index.index(t) for t in ("記事3", "記事2", "記事1", "日付なし")]
    assert positions == sorted(positions)
    assert 'href="articles/post-3.html"' in index
    assert (tmp_path / "site" / "articles" / "post-3.html").exists()
    assert (tmp_path / "site" / "style.css").exists()


def test_empty_content(tmp_path):
    assert build(tmp_path / "none", tmp_path / "site") == 0
    assert "まだ記事がない" in (tmp_path / "site" / "index.html").read_text(encoding="utf-8")


def test_inline_keeps_allowed_tags_only():
    html = '<strong>a</strong><a href="https://x.test/?a=1&amp;b=2">b</a><span>c</span><script>bad()</script><!-- x -->'
    assert inline(html) == '<strong>a</strong><a href="https://x.test/?a=1&amp;b=2">b</a>c'


def test_inline_drops_unsafe_links():
    assert inline('<a href="javascript:alert(1)">x</a>') == "x"
    assert inline('<img src=x onerror="alert(1)">y') == "y"
    assert inline("1 &lt; 2") == "1 &lt; 2"


def test_article_escapes_code_and_metadata():
    entry = _entry(1)
    entry.title = "<b>Raw</b>"
    blocks = [
        Paragraph(Text("本文")),
        Code("if a < b: print('<x>')", "Python"),
        Image("javascript:alert(1)", Text("説明")),
        Note(Text("FIG A"), None),
    ]
    html = render_article(StoredArticle(entry, "題<名>", "要約", blocks, datetime.now(timezone.utc)))
    assert "&lt;b&gt;Raw&lt;/b&gt;" in html
    assert "題&lt;名&gt;" in html
    assert "if a &lt; b: print(&#x27;&lt;x&gt;&#x27;)" in html
    assert 'src="#"' in html
    assert 'href="https://claude.dev/blog/post-1/">原文</a> を参照：FIG A' in html


def test_diagram_embeds_sanitized_svg():
    svg = '<svg class="art-diagram-wide" viewBox="0 0 1 1" onload="alert(1)"><text>Hooks</text></svg>'
    blocks = [Diagram(Text("フックの<strong>連鎖</strong>"), Text("図の説明"), [svg], "A chain of hooks")]
    html = render_article(StoredArticle(_entry(1), "題", "要約", blocks, datetime.now(timezone.utc)))
    assert '<div class="diagram-title">フックの<strong>連鎖</strong></div>' in html
    assert 'role="img" aria-label="A chain of hooks"' in html
    assert '<svg class="art-diagram-wide" viewBox="0 0 1 1"><text>Hooks</text></svg>' in html
    assert "alert" not in html
    assert "<figcaption>図の説明</figcaption>" in html

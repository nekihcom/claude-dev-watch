from pathlib import Path

import pytest

from claude_dev_watch.article import (
    ArticleParseError,
    Code,
    Diagram,
    Heading,
    Image,
    ListBlock,
    Note,
    Paragraph,
    Quote,
    Table,
    Video,
    iter_texts,
    parse_article,
)

BASE = "https://claude.dev/blog/sample/"
HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text(encoding="utf-8")


@pytest.fixture
def blocks():
    return parse_article(HTML, BASE)


def test_block_order(blocks):
    kinds = [type(b).__name__ for b in blocks]
    assert kinds == [
        "Paragraph", "Paragraph", "Video",
        "Heading", "Heading", "Heading",
        "ListBlock", "ListBlock", "Code", "Code", "Diagram", "Note", "Table", "Image", "Quote",
        "Quote", "Paragraph",
    ]  # fmt: skip


def test_inline_tags_kept_and_links_absolute(blocks):
    first, second = blocks[0], blocks[1]
    assert isinstance(first, Paragraph)
    assert "<code>inline_code()</code>" in first.text.html
    assert "<strong>bold</strong>" in first.text.html
    assert '<a href="https://example.com/docs">link</a>' in first.text.html
    assert 'href="https://claude.dev/blog/sample/#step-two"' in second.text.html
    assert 'href="https://claude.dev/blog/other/"' in second.text.html
    assert "café" in second.text.html


def test_headings_levels(blocks):
    levels = [b.level for b in blocks if isinstance(b, Heading)]
    assert levels == [1, 2, 3]


def test_nested_list(blocks):
    ul = blocks[6]
    assert isinstance(ul, ListBlock) and not ul.ordered
    assert [i.text.html for i in ul.items] == ["First item", "Second item with <code>code</code>"]
    assert ul.items[1].children[0].items[0].text.html == "Nested item"
    assert blocks[7].ordered


def test_code_is_raw_text_with_language(blocks):
    code, prompt = blocks[8], blocks[9]
    assert isinstance(code, Code)
    assert code.language == "TypeScript"
    assert code.code == "const x = 1;\n// keep <tags> as is"
    assert prompt.language == "Text"
    assert prompt.code == "/do-something now"


def test_figures(blocks):
    video, diagram, note, image = blocks[2], blocks[10], blocks[11], blocks[13]
    assert isinstance(video, Video) and video.url == "https://claude.dev/media/aaa.mp4"
    assert video.caption.html == "<b>FIG A</b> A sample video caption."
    assert isinstance(diagram, Diagram) and diagram.label.html == "How it flows"
    assert diagram.description == "Flow from A to B"
    # 画面幅ごとに描き分けた SVG を両方残し、スクリプトは取り除く
    assert len(diagram.svgs) == 2
    assert diagram.svgs[0].startswith('<svg class="art-diagram-wide" viewBox="0 0 10 10">')
    assert "alert" not in diagram.svgs[0]
    assert '<text style="fill:var(--ink)">label</text>' in diagram.svgs[0]
    # インタラクティブな図は再現できないため注記のままにする
    assert isinstance(note, Note) and note.label.html == "Interactive"
    assert isinstance(image, Image) and image.url == "https://claude.dev/media/bbb.png"


def test_table(blocks):
    table = blocks[12]
    assert isinstance(table, Table) and table.has_header
    assert [[c.html for c in r] for r in table.rows] == [
        ["Name", "Value"],
        ["<code>a</code>", "first"],
        ["b", "<strong>second</strong>"],
    ]


def test_quotes_and_thread(blocks):
    assert isinstance(blocks[14], Quote) and blocks[14].text.html == "A quoted sentence."
    assert blocks[15].text.html == "<strong>Sam</strong>: Hello there."


def test_code_is_not_translation_target(blocks):
    texts = [t.html for t in iter_texts(blocks)]
    assert not any("const x" in t for t in texts)
    assert "How it flows" in texts
    # 図中の文字は訳さない
    assert not any("label" in t or "narrow" in t for t in texts)


def test_missing_body_raises():
    with pytest.raises(ArticleParseError):
        parse_article("<html><body><p>x</p></body></html>", BASE)

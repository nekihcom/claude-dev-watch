from claude_dev_watch import refresh
from claude_dev_watch.article import Diagram, Note, Paragraph, Text
from claude_dev_watch.feed import Entry
from claude_dev_watch.refresh import merge_diagrams, refresh_figures
from claude_dev_watch.store import ContentStore

SVG = "<svg><text>x</text></svg>"


def _diagram(label="Flow", caption=None):
    return Diagram(Text(label), Text(caption) if caption else None, [SVG], "desc")


def test_replaces_notes_with_diagrams_keeping_translations():
    stored = [Paragraph(Text("本文")), Note(Text("流れ"), Text("説明")), Note(Text("操作"), None)]
    fresh = [Paragraph(Text("Body")), _diagram("Flow", "Caption"), Note(Text("Interactive"), None)]
    assert merge_diagrams(stored, fresh) == [
        Paragraph(Text("本文")),
        Diagram(Text("流れ"), Text("説明"), [SVG], "desc"),
        Note(Text("操作"), None),
    ]


def test_gives_up_when_figures_do_not_line_up():
    stored = [Note(Text("流れ"), None)]
    assert merge_diagrams(stored, [_diagram(), _diagram()]) is None
    assert merge_diagrams(stored, [_diagram(label="")]) is None
    assert merge_diagrams(stored, [_diagram(caption="Caption")]) is None


def test_refresh_rewrites_only_changed_articles(tmp_path, monkeypatch):
    store = ContentStore(tmp_path)
    for n, blocks in ((1, [Note(Text("流れ"), None)]), (2, [Paragraph(Text("図なし"))])):
        entry = Entry(f"T{n}", f"https://claude.dev/blog/post-{n}/", None, "A", "C", "S")
        store.save(entry, "題", "要約", blocks)
    monkeypatch.setattr(refresh, "fetch_html", lambda url: url)
    monkeypatch.setattr(refresh, "parse_article", lambda html, url: [_diagram()])

    assert refresh_figures(store) == 1
    first, second = store.load_all()
    assert first.blocks == [Diagram(Text("流れ"), None, [SVG], "desc")]
    assert second.blocks == [Paragraph(Text("図なし"))]
    # 2 回目は変更がないため書き換えない
    assert refresh_figures(store) == 0

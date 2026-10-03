from claude_dev_watch.article import Code, ListBlock, ListItem, Paragraph, Table, Text
from claude_dev_watch.notion import MAX_CHILDREN, rich_text, to_blocks


def test_rich_text_annotations_and_links():
    rt = rich_text('A <strong>b</strong> <code>c()</code> <a href="https://x.dev/">d</a>')
    assert [r["text"]["content"] for r in rt] == ["A ", "b", " ", "c()", " ", "d"]
    assert rt[1]["annotations"]["bold"]
    assert rt[3]["annotations"]["code"]
    assert rt[5]["text"]["link"] == {"url": "https://x.dev/"}


def test_rich_text_drops_non_http_links():
    rt = rich_text('<a href="javascript:alert(1)">x</a>')
    assert rt[0]["text"]["link"] is None


def test_long_paragraph_split_to_2000_chars():
    blocks = to_blocks([Paragraph(Text("a" * 4500))])
    contents = [r["text"]["content"] for r in blocks[0]["paragraph"]["rich_text"]]
    assert [len(c) for c in contents] == [2000, 2000, 500]


def test_too_many_rich_texts_split_into_blocks():
    html = " ".join(f"<strong>{i}</strong>" for i in range(150))
    blocks = to_blocks([Paragraph(Text(html))])
    assert len(blocks) == 3  # 太字 150 + 空白 149 = 299 要素
    assert all(len(b["paragraph"]["rich_text"]) <= 100 for b in blocks)


def test_code_block_language_and_split():
    blocks = to_blocks([Code("x" * 2500, "TypeScript"), Code("y", "PROMPT")])
    assert blocks[0]["code"]["language"] == "typescript"
    assert [len(r["text"]["content"]) for r in blocks[0]["code"]["rich_text"]] == [2000, 500]
    assert blocks[1]["code"]["language"] == "plain text"


def test_nested_list_children():
    lb = ListBlock(False, [ListItem(Text("a"), [ListBlock(True, [ListItem(Text("b"))])])])
    blocks = to_blocks([lb])
    child = blocks[0]["bulleted_list_item"]["children"][0]
    assert child["type"] == "numbered_list_item"


def test_table_rows_padded():
    t = Table([[Text("h1"), Text("h2")], [Text("only")]], has_header=True)
    block = to_blocks([t])[0]["table"]
    assert block["table_width"] == 2 and block["has_column_header"]
    assert block["children"][1]["table_row"]["cells"][1] == []


def test_many_blocks_are_chunkable():
    blocks = to_blocks([Paragraph(Text(str(i))) for i in range(250)])
    chunks = [blocks[i : i + MAX_CHILDREN] for i in range(0, len(blocks), MAX_CHILDREN)]
    assert [len(c) for c in chunks] == [100, 100, 50]

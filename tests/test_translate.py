from claude_dev_watch import translate
from claude_dev_watch.translate import _batches, count_characters


def test_batches_respect_count_limit():
    texts = ["x"] * 120
    sizes = [len(b) for b in _batches(list(range(120)), texts)]
    assert sizes == [50, 50, 20]


def test_batches_respect_byte_limit(monkeypatch):
    monkeypatch.setattr(translate, "MAX_BYTES_PER_REQUEST", 10)
    texts = ["aaaa", "bbbb", "cccc"]
    assert list(_batches([0, 1, 2], texts)) == [[0, 1], [2]]


def test_count_characters_ignores_blank():
    assert count_characters(["abc", "  ", "de"]) == 5


def test_protect_terms_wraps_text_only():
    from claude_dev_watch.translate import protect_terms

    html = 'Use Claude Code with <a href="https://claude.dev/Claude">Claude</a> and <code>Opus</code>. Claudette'
    assert protect_terms(html) == (
        'Use <keep>Claude Code</keep> with <a href="https://claude.dev/Claude"><keep>Claude</keep></a>'
        " and <code><keep>Opus</keep></code>. Claudette"
    )


def test_unprotect_terms_roundtrip():
    from claude_dev_watch.translate import protect_terms, unprotect_terms

    html = 'Claude Code と <a href="https://x.dev/">Claude</a>'
    assert unprotect_terms(protect_terms(html)) == html


def test_protect_terms_uppercase_heading_but_not_common_nouns():
    from claude_dev_watch.translate import protect_terms

    assert protect_terms("THE CLAUDE CODE GUIDE") == "THE <keep>CLAUDE CODE</keep> GUIDE"
    assert protect_terms("cut some slack, write a haiku") == "cut some slack, write a haiku"

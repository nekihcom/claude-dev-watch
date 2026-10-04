from datetime import datetime, timezone
from pathlib import Path

from claude_dev_watch.article import parse_article
from claude_dev_watch.feed import Entry
from claude_dev_watch.store import ContentStore

HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text(encoding="utf-8")


def _entry(published=datetime(2026, 10, 1, tzinfo=timezone.utc)) -> Entry:
    return Entry(
        title="Title",
        url="https://claude.dev/blog/post-1/",
        published=published,
        author="Author",
        category="Tutorials",
        summary="Summary",
    )


def test_round_trip_keeps_all_blocks(tmp_path):
    blocks = parse_article(HTML, "https://claude.dev/blog/post-1/")
    store = ContentStore(tmp_path)
    store.save(_entry(), "タイトル", "要約", blocks)

    [loaded] = store.load_all()
    assert loaded.slug == "post-1"
    assert loaded.entry == _entry()
    assert (loaded.title_ja, loaded.summary_ja) == ("タイトル", "要約")
    # 中間表現がすべての種類のブロックで欠けずに復元できること
    assert loaded.blocks == blocks


def test_published_may_be_missing(tmp_path):
    store = ContentStore(tmp_path)
    store.save(_entry(published=None), "t", "s", [])
    assert store.load_all()[0].entry.published is None


def test_existing_urls(tmp_path):
    store = ContentStore(tmp_path / "missing")
    assert store.existing_urls() == set()
    store.save(_entry(), "t", "s", [])
    assert store.existing_urls() == {"https://claude.dev/blog/post-1/"}
    assert not list((tmp_path / "missing").glob("*.tmp"))

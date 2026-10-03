from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_dev_watch import main as main_mod
from claude_dev_watch.article import Paragraph, Text
from claude_dev_watch.feed import Entry
from claude_dev_watch.notion import NotionStore, to_blocks

HTML = (Path(__file__).parent / "fixtures" / "article.html").read_text(encoding="utf-8")


def _entry(n: int) -> Entry:
    return Entry(
        title=f"Title {n}",
        url=f"https://claude.dev/blog/post-{n}/",
        published=datetime(2026, 10, n, tzinfo=timezone.utc),
        author="Author",
        category="Tutorials",
        summary="Summary",
    )


class FakeStore:
    def __init__(self, known=()):
        self.known = set(known)
        self.created = []

    def existing_urls(self):
        return set(self.known)

    def create_page(self, entry, title_ja, summary_ja, blocks):
        self.created.append(entry.url)
        return entry.url


class FakeTranslator:
    def __init__(self, remaining):
        self.remaining = remaining
        self.calls = 0

    def remaining_characters(self):
        return self.remaining

    def translate(self, texts):
        self.calls += 1
        return [f"[ja]{t}" for t in texts]


@pytest.fixture
def env(monkeypatch):
    def setup(entries, store, translator, html=lambda url: HTML):
        monkeypatch.setenv("NOTION_TOKEN", "x")
        monkeypatch.setenv("NOTION_DATABASE_ID", "x")
        monkeypatch.setenv("DEEPL_API_KEY", "x")
        monkeypatch.setattr(main_mod, "fetch_entries", lambda: entries)
        monkeypatch.setattr(main_mod, "NotionStore", lambda *a: store)
        monkeypatch.setattr(main_mod, "DeepLTranslator", lambda *a: translator)
        monkeypatch.setattr(main_mod, "fetch_html", html)

    return setup


def test_skips_already_registered(env):
    store = FakeStore(known=[_entry(1).url])
    env([_entry(1), _entry(2)], store, FakeTranslator(None))
    assert main_mod.main([]) == 0
    assert store.created == [_entry(2).url]


def test_second_run_creates_nothing(env):
    store = FakeStore()
    env([_entry(1)], store, FakeTranslator(None))
    main_mod.main([])
    store.known.update(store.created)
    main_mod.main([])
    assert store.created == [_entry(1).url]


def test_quota_shortage_stops_without_failure(env):
    store = FakeStore()
    translator = FakeTranslator(remaining=100)
    env([_entry(1), _entry(2)], store, translator)
    assert main_mod.main([]) == 0
    assert store.created == [] and translator.calls == 0


def test_one_failure_does_not_stop_others(env):
    store = FakeStore()

    def html(url):
        if "post-1" in url:
            raise RuntimeError("boom")
        return HTML

    env([_entry(1), _entry(2)], store, FakeTranslator(None), html)
    assert main_mod.main([]) == 1
    assert store.created == [_entry(2).url]


def test_limit(env):
    store = FakeStore()
    env([_entry(1), _entry(2), _entry(3)], store, FakeTranslator(None))
    main_mod.main(["--limit", "2"])
    assert store.created == [_entry(1).url, _entry(2).url]


def test_dry_run_writes_markdown(env, tmp_path):
    env([_entry(1)], FakeStore(), FakeTranslator(None))
    assert main_mod.main(["--dry-run", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "post-1.md").read_text(encoding="utf-8")
    assert md.startswith("# [ja]Title 1")
    assert "const x = 1;" in md  # コードは翻訳されない


# ---------- NotionStore ----------


class FakeClient:
    def __init__(self, fail_on_append=False):
        self.fail_on_append = fail_on_append
        self.create_children = None
        self.appended = []
        self.trashed = []
        outer = self

        class Pages:
            def create(self, **kw):
                outer.create_children = kw["children"]
                return {"id": "page-1", "url": "https://notion.so/page-1"}

            def update(self, page_id, **kw):
                outer.trashed.append((page_id, kw))

        class Children:
            def append(self, block_id, children):
                if outer.fail_on_append:
                    raise RuntimeError("api error")
                outer.appended.append(len(children))

        class Blocks:
            children = Children()

        self.pages = Pages()
        self.blocks = Blocks()


def _store(client) -> NotionStore:
    store = NotionStore.__new__(NotionStore)
    store._client = client
    store._data_source_id = "ds"
    return store


def test_create_page_appends_in_chunks_of_100():
    client = FakeClient()
    blocks = to_blocks([Paragraph(Text(str(i))) for i in range(250)])
    _store(client).create_page(_entry(1), "t", "s", blocks)
    # 先頭の原文リンク callout を含めて 251 ブロック
    assert len(client.create_children) == 100
    assert client.appended == [100, 51]


def test_partial_page_is_trashed_on_failure():
    client = FakeClient(fail_on_append=True)
    blocks = to_blocks([Paragraph(Text(str(i))) for i in range(150)])
    with pytest.raises(RuntimeError):
        _store(client).create_page(_entry(1), "t", "s", blocks)
    assert client.trashed == [("page-1", {"in_trash": True})]

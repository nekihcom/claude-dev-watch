from datetime import datetime, timezone
from pathlib import Path

import pytest

from claude_dev_watch import main as main_mod
from claude_dev_watch.feed import Entry
from claude_dev_watch.store import ContentStore

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

    def save(self, entry, title_ja, summary_ja, blocks):
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
        monkeypatch.setenv("DEEPL_API_KEY", "x")
        monkeypatch.setattr(main_mod, "fetch_entries", lambda: entries)
        monkeypatch.setattr(main_mod, "ContentStore", lambda *a: store)
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


def test_saves_json_and_skips_it_next_time(monkeypatch, tmp_path):
    content = tmp_path / "content"
    translator = FakeTranslator(None)
    monkeypatch.setenv("DEEPL_API_KEY", "x")
    monkeypatch.setattr(main_mod, "fetch_entries", lambda: [_entry(1)])
    monkeypatch.setattr(main_mod, "DeepLTranslator", lambda *a: translator)
    monkeypatch.setattr(main_mod, "fetch_html", lambda url: HTML)

    assert main_mod.main(["--content", str(content)]) == 0
    assert (content / "post-1.json").exists()
    assert ContentStore(content).load_all()[0].title_ja == "[ja]Title 1"

    assert main_mod.main(["--content", str(content)]) == 0
    assert translator.calls == 1


def test_build_site_command(env, tmp_path):
    env([_entry(1)], ContentStore(tmp_path / "content"), FakeTranslator(None))
    main_mod.main(["--content", str(tmp_path / "content")])
    out = tmp_path / "site"
    assert main_mod.main(["--content", str(tmp_path / "content"), "build-site", "--site-out", str(out)]) == 0
    assert (out / "index.html").exists()
    assert (out / "articles" / "post-1.html").exists()

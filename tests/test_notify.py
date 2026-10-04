from pathlib import Path

import pytest
import requests

from claude_dev_watch import notify as notify_mod
from claude_dev_watch.notify import notify

SITE = "https://example.github.io/claude-dev-watch/"


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))


@pytest.fixture
def posts(monkeypatch):
    calls = []

    def post(url, json, headers, timeout):
        calls.append((url, json))
        return FakeResponse()

    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.delenv("NTFY_SERVER", raising=False)
    monkeypatch.setattr(notify_mod.requests, "post", post)
    return calls


def test_single_article_links_to_its_page(posts):
    assert notify([Path("content/post-1.json")], SITE) == 0
    assert posts == [
        (
            "https://ntfy.sh",
            {
                "topic": "my-topic",
                "message": "claude-dev-watch 新着 1 件",
                "click": "https://example.github.io/claude-dev-watch/articles/post-1.html",
            },
        )
    ]


def test_multiple_articles_link_to_index(posts):
    assert notify([Path("content/post-1.json"), Path("content/post-2.json")], SITE.rstrip("/")) == 0
    _, payload = posts[0]
    assert payload["message"] == "claude-dev-watch 新着 2 件"
    assert payload["click"] == SITE


def test_custom_server(posts, monkeypatch):
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com/")
    notify([Path("content/post-1.json")], SITE)
    assert posts[0][0] == "https://ntfy.example.com"


def test_no_articles_sends_nothing(posts):
    assert notify([], SITE) == 0
    assert posts == []


def test_missing_topic_skips(posts, monkeypatch):
    monkeypatch.delenv("NTFY_TOPIC")
    assert notify([Path("content/post-1.json")], SITE) == 0
    assert posts == []


def test_send_failure_returns_1(monkeypatch):
    monkeypatch.setenv("NTFY_TOPIC", "my-topic")
    monkeypatch.setattr(notify_mod.requests, "post", lambda *a, **k: FakeResponse(500))
    assert notify([Path("content/post-1.json")], SITE) == 1

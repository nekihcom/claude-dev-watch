from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import requests

from . import USER_AGENT

FEED_URL = "https://claude.dev/rss.xml"


@dataclass
class Entry:
    title: str
    url: str
    published: datetime | None
    author: str
    category: str
    summary: str


def fetch_entries(feed_url: str = FEED_URL) -> list[Entry]:
    """RSS の記事を公開日の古い順に返す。"""
    # 既定の User-Agent（Python-urllib）だとサイトに 403 で拒否されるため、requests で明示して取得する
    res = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=30)
    res.raise_for_status()
    parsed = feedparser.parse(res.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"RSS を解析できない: {parsed.bozo_exception}")

    entries = [_to_entry(e) for e in parsed.entries]
    # DeepL の枠が途中で尽きたとき、新しい記事ではなく古い記事から順に訳し終えるため古い順に並べる
    entries.sort(key=lambda e: e.published or datetime.min.replace(tzinfo=timezone.utc))
    return entries


def _to_entry(e: feedparser.FeedParserDict) -> Entry:
    published = None
    if e.get("published_parsed"):
        published = datetime.fromtimestamp(calendar.timegm(e.published_parsed), tz=timezone.utc)
    tags = e.get("tags") or []
    return Entry(
        title=e.get("title", "").strip(),
        url=(e.get("id") or e.get("link") or "").strip(),
        published=published,
        author=e.get("author", "").strip(),
        category=tags[0]["term"].strip() if tags else "",
        summary=e.get("summary", "").strip(),
    )

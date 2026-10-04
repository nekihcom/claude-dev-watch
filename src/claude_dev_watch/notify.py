"""新しく追加された訳文を ntfy でスマートフォンに通知する。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

from . import USER_AGENT

log = logging.getLogger(__name__)

DEFAULT_SERVER = "https://ntfy.sh"


def notify(paths: list[Path], site_url: str) -> int:
    if not paths:
        log.info("新着記事がないため通知しない")
        return 0
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        # ローカル実行やフォーク先で Secrets がなくてもジョブを落とさないため、失敗扱いにしない
        log.info("NTFY_TOPIC が未設定のため通知しない")
        return 0
    server = (os.environ.get("NTFY_SERVER") or DEFAULT_SERVER).rstrip("/")

    # ntfy は本文が空だと既定の文言（triggered）を出すため、件数だけを本文に入れる
    payload = {"topic": topic, "message": f"claude-dev-watch 新着 {len(paths)} 件", "click": _click_url(paths, site_url)}
    # ヘッダーで送ると日本語を RFC 2047 でエンコードする必要があるため、JSON で送る
    try:
        res = requests.post(server, json=payload, headers={"User-Agent": USER_AGENT}, timeout=30)
        res.raise_for_status()
    except requests.RequestException:
        log.exception("通知の送信に失敗した")
        return 1
    log.info("通知を送信した: %d 件", len(paths))
    return 0


def _click_url(paths: list[Path], site_url: str) -> str:
    base = site_url.rstrip("/") + "/"
    if len(paths) == 1:
        return f"{base}articles/{paths[0].stem}.html"
    return base

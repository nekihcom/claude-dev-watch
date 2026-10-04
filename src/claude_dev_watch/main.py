from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .article import fetch_html, iter_texts, parse_article
from .config import load_env
from .feed import Entry, fetch_entries
from .markdown import inline, render
from .site import build
from .store import ContentStore, slug_of
from .translate import DeepLTranslator, IdentityTranslator, Translator, count_characters

log = logging.getLogger("claude_dev_watch")

# 見積もりの誤差や翌日以降の記事のために残しておく DeepL の文字数
USAGE_MARGIN = 10_000


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    # 通信ごとに INFO を出すライブラリがあり、処理の要点が埋もれるため警告以上だけにする
    for name in ("deepl", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if args.command == "build-site":
        build(Path(args.content), Path(args.site_out))
        return 0

    entries = fetch_entries()
    log.info("RSS の記事数: %d", len(entries))

    store = None
    if not args.dry_run:
        store = ContentStore(Path(args.content))
        known = store.existing_urls()
        entries = [e for e in entries if e.url not in known]
    if args.url:
        entries = [e for e in entries if e.url == args.url]
    if args.limit is not None:
        entries = entries[: args.limit]
    log.info("処理対象: %d 件", len(entries))
    if not entries:
        return 0

    translator: Translator = (
        IdentityTranslator()
        if args.no_translate
        else DeepLTranslator(_env("DEEPL_API_KEY"), os.environ.get("DEEPL_GLOSSARY_ID") or None)
    )
    remaining = translator.remaining_characters()
    if remaining is not None:
        log.info("DeepL の残り文字数: %d", remaining)

    failures = 0
    for entry in entries:
        try:
            remaining = _process(entry, translator, store, remaining, Path(args.out))
        except QuotaExceeded as e:
            # 枠が足りないのは失敗ではない。未保存のまま残し、翌月以降の実行で拾わせる
            _warn(str(e))
            break
        except Exception:
            failures += 1
            log.exception("記事の処理に失敗した: %s", entry.url)

    if failures:
        log.error("失敗した記事: %d 件", failures)
        return 1
    return 0


class QuotaExceeded(Exception):
    pass


def _process(
    entry: Entry, translator: Translator, store: ContentStore | None, remaining: int | None, out: Path
) -> int | None:
    log.info("処理開始: %s", entry.url)
    blocks = parse_article(fetch_html(entry.url), entry.url)
    texts = list(iter_texts(blocks))
    sources = [_escape(entry.title), _escape(entry.summary)] + [t.html for t in texts]

    needed = count_characters(sources)
    if remaining is not None and needed > remaining - USAGE_MARGIN:
        raise QuotaExceeded(
            f"DeepL の残り枠が足りないため中断する（必要 約{needed} / 残り {remaining}）: {entry.url}"
        )

    translated = translator.translate(sources)
    title_ja, summary_ja = inline(translated[0]), inline(translated[1])
    for t, html in zip(texts, translated[2:]):
        t.html = html

    if store is None:
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{slug_of(entry.url)}.md"
        path.write_text(render(entry, title_ja, summary_ja, blocks), encoding="utf-8")
        log.info("Markdown を出力した: %s（%d 文字）", path, needed)
    else:
        path = store.save(entry, title_ja, summary_ja, blocks)
        log.info("訳文を保存した: %s（%d 文字）", path, needed)

    return None if remaining is None else remaining - needed


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"環境変数 {name} が設定されていない")
    return value


def _warn(message: str) -> None:
    # GitHub Actions のジョブ概要に警告として表示させる
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning::{message}")
    log.warning(message)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="claude.dev ブログの新着記事を日本語訳して保存し、静的サイトを生成する")
    p.add_argument("--content", default="content", help="訳文（JSON）の保存先（既定: content）")
    sub = p.add_subparsers(dest="command")
    site = sub.add_parser("build-site", help="保存した訳文から GitHub Pages 用のサイトを生成する")
    site.add_argument("--site-out", default="_site", help="サイトの出力先（既定: _site）")
    p.add_argument("--dry-run", action="store_true", help="訳文を保存せず、Markdown をローカルに出力する")
    p.add_argument("--limit", type=int, help="処理する記事数の上限（古い順）")
    p.add_argument("--url", help="指定した URL の記事だけを処理する")
    p.add_argument("--no-translate", action="store_true", help="DeepL を呼ばずに原文のまま処理する（構造確認用）")
    p.add_argument("--out", default="out", help="--dry-run の出力先（既定: out）")
    return p.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())

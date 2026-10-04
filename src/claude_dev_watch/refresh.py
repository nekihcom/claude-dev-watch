"""保存済みの訳文のうち、注記にしていた図を、原文から取り直した SVG の図に置き換える。

図に SVG を埋め込む前に保存した記事を、DeepL で翻訳し直さずに作り直すためのもの。
タイトルとキャプションは保存済みの訳文を使い、SVG だけを原文から補う。
"""

from __future__ import annotations

import logging

from .article import Block, Diagram, Note, fetch_html, parse_article
from .store import ContentStore, StoredArticle

log = logging.getLogger(__name__)


def refresh_figures(store: ContentStore) -> int:
    """全記事の図を補い、更新した記事数を返す。"""
    updated = 0
    for article in store.load_all():
        if not any(isinstance(b, Note) for b in article.blocks):
            continue
        try:
            fresh = parse_article(fetch_html(article.entry.url), article.entry.url)
        except Exception:
            log.exception("原文の取得に失敗した: %s", article.entry.url)
            continue
        blocks = merge_diagrams(article.blocks, fresh)
        if blocks is None:
            log.warning("原文の図の数や並びが保存時と異なるため、更新しない: %s", article.entry.url)
            continue
        if blocks == article.blocks:
            continue
        store.write(StoredArticle(article.entry, article.title_ja, article.summary_ja, blocks, article.translated_at))
        log.info("図を補った: %s", article.slug)
        updated += 1
    return updated


def merge_diagrams(stored: list[Block], fresh: list[Block]) -> list[Block] | None:
    """保存済みの注記を、原文から取り直した図で置き換える。図の対応が取れなければ None を返す。

    図は本文の直下にしか現れないため、注記と図を出現順に突き合わせる。
    原文が更新されて図が増減していると別の図を当てはめてしまうため、数とタイトルの有無が揃わなければ諦める。
    """
    old = [i for i, b in enumerate(stored) if isinstance(b, Note)]
    new = [b for b in fresh if isinstance(b, (Note, Diagram))]
    if len(old) != len(new):
        return None
    blocks = list(stored)
    for i, figure in zip(old, new):
        note = stored[i]
        assert isinstance(note, Note)
        if bool(note.label.html) != bool(figure.label.html) or (note.caption is None) != (figure.caption is None):
            return None
        if isinstance(figure, Diagram):
            blocks[i] = Diagram(note.label, note.caption, figure.svgs, figure.description)
    return blocks

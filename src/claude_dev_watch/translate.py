from __future__ import annotations

import logging
import re
from typing import Protocol

import deepl

log = logging.getLogger(__name__)

# DeepL API の 1 リクエストあたりの上限（テキスト 50 件・本文 128 KiB）に余裕を持たせた値
MAX_TEXTS_PER_REQUEST = 50
MAX_BYTES_PER_REQUEST = 100 * 1024

# DeepL は「Claude」を「クロード」のようにカタカナへ訳してしまうため、製品名などは原文のまま残す。
# 長い語を先に並べ、「Claude Code」が「Claude」より先に一致するようにしている
KEEP_TERMS = [
    "Claude Code",
    "Claude API",
    "Agent SDK",
    "Terminal-Bench",
    "Anthropic",
    "Claude",
    "Opus",
    "Sonnet",
    "Haiku",
    "Fable",
    "GitHub",
    "Slack",
    "MCP",
]
KEEP_TAG = "keep"
# サイトの h2 見出しは全文が大文字（例: THE CLAUDE CODE GUIDE）のため、大文字表記も対象にする。
# 大文字小文字を無視しないのは、普通名詞の slack や haiku まで訳さずに残してしまうため
_TERM_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for t in KEEP_TERMS for v in dict.fromkeys([t, t.upper()])) + r")\b"
)
_TAG_SPLIT_RE = re.compile(r"(<[^>]*>)")
_KEEP_TAG_RE = re.compile(rf"</?{KEEP_TAG}>")


class Translator(Protocol):
    def remaining_characters(self) -> int | None: ...

    def translate(self, texts: list[str]) -> list[str]: ...


class DeepLTranslator:
    def __init__(self, api_key: str, glossary_id: str | None = None) -> None:
        self._client = deepl.DeepLClient(api_key)
        self._glossary = glossary_id

    def remaining_characters(self) -> int | None:
        usage = self._client.get_usage().character
        if not usage.valid or usage.limit is None:
            return None
        return usage.limit - usage.count

    def translate(self, texts: list[str]) -> list[str]:
        results = list(texts)
        # 空文字を送ると DeepL がエラーを返すため、中身のあるものだけを送る
        targets = [i for i, t in enumerate(texts) if t.strip()]
        for batch in _batches(targets, texts):
            translated = self._client.translate_text(
                [protect_terms(texts[i]) for i in batch],
                source_lang="EN",
                target_lang="JA",
                tag_handling="html",
                # インラインコードは識別子やコマンドなので訳さない
                ignore_tags=["code", KEEP_TAG],
                glossary=self._glossary,
            )
            for i, r in zip(batch, translated):
                results[i] = unprotect_terms(r.text)
        return results


def protect_terms(html: str) -> str:
    """固有名詞を翻訳対象外のタグで囲む。タグの中（href 属性など）は書き換えない。"""
    parts = _TAG_SPLIT_RE.split(html)
    for i in range(0, len(parts), 2):
        parts[i] = _TERM_RE.sub(lambda m: f"<{KEEP_TAG}>{m.group(0)}</{KEEP_TAG}>", parts[i])
    return "".join(parts)


def unprotect_terms(html: str) -> str:
    return _KEEP_TAG_RE.sub("", html)


class IdentityTranslator:
    """翻訳せずに原文を返す。API キーなしで構造だけを確認するときに使う。"""

    def remaining_characters(self) -> int | None:
        return None

    def translate(self, texts: list[str]) -> list[str]:
        return list(texts)


def _batches(indexes: list[int], texts: list[str]):
    batch: list[int] = []
    size = 0
    for i in indexes:
        n = len(texts[i].encode("utf-8"))
        if batch and (len(batch) >= MAX_TEXTS_PER_REQUEST or size + n > MAX_BYTES_PER_REQUEST):
            yield batch
            batch, size = [], 0
        batch.append(i)
        size += n
    if batch:
        yield batch


def count_characters(texts: list[str]) -> int:
    # DeepL がタグを課金対象に含めるかに依存しないよう、タグ込みの文字数で多めに見積もる
    return sum(len(t) for t in texts if t.strip())

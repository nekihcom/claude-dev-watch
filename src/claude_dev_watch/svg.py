"""原文のインライン SVG を、公開ページに埋め込んでも安全な形に絞り込む。

外部サイトの SVG をそのまま埋め込むと、script やイベント属性、外部リソースの読み込みまで持ち込みうる。
描画に必要な要素と属性だけを残し、それ以外は捨てる。
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

# use・image・a・foreignObject・script・アニメーション要素は、外部参照やスクリプト実行の経路になるため入れない
_ELEMENTS = {
    "svg", "g", "defs", "title", "desc", "style",
    "path", "line", "polyline", "polygon", "rect", "circle", "ellipse",
    "text", "tspan",
    "marker", "clippath", "mask", "lineargradient", "radialgradient", "stop", "pattern",
}  # fmt: skip

_ATTRIBUTES = {
    "id", "class", "style", "xmlns", "viewbox", "preserveaspectratio", "width", "height", "transform",
    "aria-hidden", "focusable", "role", "aria-label",
    "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry", "d", "points", "dx", "dy", "rotate",
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset", "stroke-miterlimit", "opacity", "paint-order",
    "font-family", "font-size", "font-weight", "font-style", "letter-spacing", "text-anchor",
    "dominant-baseline", "alignment-baseline", "textlength", "lengthadjust",
    "clip-path", "clip-rule", "mask", "marker-start", "marker-mid", "marker-end",
    "markerwidth", "markerheight", "markerunits", "refx", "refy", "orient",
    "offset", "stop-color", "stop-opacity", "gradientunits", "gradienttransform",
    "patternunits", "patterntransform", "clippathunits", "maskunits",
}  # fmt: skip

# html.parser は名前を小文字にする。ブラウザは HTML 中の SVG を補正するが、出力側でも正しい表記に戻しておく
_CAMEL = {
    name.lower(): name
    for name in (
        "viewBox", "preserveAspectRatio", "textLength", "lengthAdjust", "markerWidth", "markerHeight",
        "markerUnits", "refX", "refY", "gradientUnits", "gradientTransform", "patternUnits",
        "patternTransform", "clipPathUnits", "maskUnits", "clipPath", "linearGradient", "radialGradient",
    )
}  # fmt: skip

# 同じ文書内の参照（url(#id)）以外の url() や @import は、外部リソースの読み込みになるため認めない
_UNSAFE_CSS = re.compile(r"url\(\s*['\"]?(?!#)|@import|expression\(|javascript:|\\", re.IGNORECASE)


def sanitize_svg(markup: str) -> str:
    """SVG のマークアップを、許可した要素と属性だけに絞って文字列に戻す。SVG がなければ空文字を返す。"""
    svg = BeautifulSoup(markup, "html.parser").find("svg")
    return _element(svg) if isinstance(svg, Tag) else ""


def _element(el: Tag) -> str:
    if el.name not in _ELEMENTS:
        return ""
    name = _CAMEL.get(el.name, el.name)
    attrs = "".join(f' {_CAMEL.get(k, k)}="{_escape(v)}"' for k, v in _attributes(el))
    if el.name == "style":
        css = el.get_text()
        return f"<style>{_escape(css)}</style>" if not _UNSAFE_CSS.search(css) else ""
    inner = "".join(_node(n) for n in el.children)
    return f"<{name}{attrs}>{inner}</{name}>"


def _attributes(el: Tag):
    for key, value in el.attrs.items():
        if isinstance(value, list):
            value = " ".join(value)
        if key not in _ATTRIBUTES or _UNSAFE_CSS.search(value):
            continue
        yield key, value


def _node(node) -> str:
    if isinstance(node, Comment):
        return ""
    if isinstance(node, NavigableString):
        return _escape(str(node))
    if isinstance(node, Tag):
        return _element(node)
    return ""


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

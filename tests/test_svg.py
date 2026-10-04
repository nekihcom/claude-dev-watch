from claude_dev_watch.svg import sanitize_svg


def test_keeps_drawing_and_restores_camel_case():
    svg = '<svg viewBox="0 0 10 10" class="a b"><g transform="translate(1 2)"><path d="M0 0L1 1" style="stroke:var(--ink)"/></g></svg>'
    assert sanitize_svg(svg) == (
        '<svg viewBox="0 0 10 10" class="a b"><g transform="translate(1 2)">'
        '<path d="M0 0L1 1" style="stroke:var(--ink)"></path></g></svg>'
    )


def test_drops_scripts_handlers_and_external_references():
    svg = (
        '<svg onload="alert(1)"><script>alert(2)</script>'
        '<foreignObject><div>x</div></foreignObject>'
        '<a href="javascript:alert(3)"><text>link</text></a>'
        '<use href="https://evil.test/x.svg#a"/>'
        '<rect style="fill:url(https://evil.test/t.png)" width="1"/>'
        '<rect marker-end="url(#arrow)"/>'
        "<style>@import url(https://evil.test/a.css);</style>"
        "<text>ok &lt; 1</text></svg>"
    )
    assert sanitize_svg(svg) == '<svg><rect width="1"></rect><rect marker-end="url(#arrow)"></rect><text>ok &lt; 1</text></svg>'


def test_keeps_safe_style_element():
    assert sanitize_svg("<svg><style>#d .m{font-weight:500}</style></svg>") == "<svg><style>#d .m{font-weight:500}</style></svg>"


def test_returns_empty_without_svg():
    assert sanitize_svg("<div>no svg</div>") == ""

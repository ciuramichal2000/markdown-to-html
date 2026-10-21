import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
from html.parser import HTMLParser

import pytest

from mdhtml import convert

# Everything the converter is allowed to emit, and where each attribute may appear.
ALLOWED_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "strong", "em", "code", "pre", "a", "ul", "ol", "li",
    "blockquote", "hr", "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {
    ("a", "href"), ("a", "title"), ("code", "class"), ("ol", "start"), ("th", "style"), ("td", "style"),
}
SAFE_SCHEMES = {"http", "https", "mailto"}
_SCHEME = re.compile(r"[a-z][a-z0-9+.\-]*:", re.IGNORECASE)


def browser_scheme(url):
    """Scheme a browser would act on, or None for a relative reference.

    Browsers drop leading control characters/spaces and any tab or newline
    before parsing, which is exactly what makes "java<TAB>script:" dangerous.
    """
    cleaned = re.sub(r"[\t\r\n]", "", url.lstrip("".join(chr(c) for c in range(0x21))))
    found = _SCHEME.match(cleaned)
    return found.group()[:-1].lower() if found else None


class _Inspector(HTMLParser):
    """Re-parses output the way a browser would, independently of the converter's own logic."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attributes.extend((tag, name, value) for name, value in attrs)

    handle_startendtag = handle_starttag


def inspect(html_text):
    inspector = _Inspector()
    inspector.feed(html_text)
    inspector.close()
    return inspector


HOSTILE_INPUTS = [
    "<script>alert(1)</script>",
    "Hello <img src=x onerror=alert(1)> there",
    "# <script>alert(1)</script>",
    "- <b onmouseover=x>item</b>",
    "1. <iframe src=\"javascript:alert(1)\"></iframe>",
    "> <iframe src=\"javascript:alert(1)\"></iframe>",
    "| <img src=x onerror=y> |\n|---|\n| <svg onload=z> |",
    "[<script>x</script>](http://a.b)",
    "`<script>alert(1)</script>`",
    "```\"><script>alert(1)</script>\n<script>alert(2)</script>\n```",
    "[x](javascript:alert(1))",
    "[x](  JaVaScRiPt:alert(1))",
    "[x](data:text/html,<script>alert(1)</script>)",
    "[x](vbscript:msgbox(1))",
    "[x](http://a.b \"<script>alert(1)</script>\")",
    "[x](\"><script>alert(1)</script>)",
    "[x](&#x6A;avascript:alert(1))",
    "<a href=\"javascript:alert(1)\">click</a>",
    "![x](javascript:alert(1))",
    "<<script>script>alert(1)<</script>/script>",
    "*<script>*alert(1)*</script>*",
    "<!-- comment --><style>body{display:none}</style>",
    "<svg/onload=alert(1)>",
    "&lt;script&gt;alert(1)&lt;/script&gt;",
]


def test_the_inspector_detects_dangerous_markup():
    # Guards the tests below: if the inspector were blind they would pass for the wrong reason.
    found = inspect('<p onclick="x"><img src="y"></p>')
    assert found.tags == ["p", "img"]
    assert ("p", "onclick", "x") in found.attributes


def test_raw_html_is_shown_as_text():
    assert convert("<script>alert(1)</script>") == "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n"
    assert convert("a <b>bold</b> & c") == "<p>a &lt;b&gt;bold&lt;/b&gt; &amp; c</p>\n"


def test_existing_entities_are_not_decoded():
    assert convert("&lt;b&gt; &#60;") == "<p>&amp;lt;b&amp;gt; &amp;#60;</p>\n"


def test_javascript_link_loses_its_anchor():
    assert convert("[x](javascript:alert(1))") == "<p>x</p>\n"


def test_javascript_link_in_every_case_and_with_hidden_characters():
    for target in ["JAVASCRIPT:alert(1)", " javascript:alert(1)", "javaScript:alert(1)"]:
        assert convert(f"[x]({target})") == "<p>x</p>\n"
    # A tab breaks the link syntax itself, so the text stays inert and no anchor appears.
    assert "<a" not in convert("[x](java\tscript:alert(1))")


def test_unsafe_scheme_check_is_applied_inside_every_container():
    assert convert("- [x](javascript:1)") == "<ul>\n<li>x</li>\n</ul>\n"
    assert convert("> [x](javascript:1)") == "<blockquote>\n<p>x</p>\n</blockquote>\n"
    assert convert("# [x](javascript:1)") == "<h1>x</h1>\n"
    assert "<a" not in convert("| [x](javascript:1) |\n|---|\n| [y](javascript:2) |")


@pytest.mark.parametrize("source", HOSTILE_INPUTS)
def test_output_for_hostile_input_contains_only_allowed_markup(source):
    found = inspect(convert(source))
    assert set(found.tags) <= ALLOWED_TAGS
    for tag, name, value in found.attributes:
        assert (tag, name) in ALLOWED_ATTRIBUTES, f"unexpected attribute {name} on <{tag}>"
        if name == "href":
            assert browser_scheme(value) in {None} | SAFE_SCHEMES


@pytest.mark.parametrize("source", HOSTILE_INPUTS)
def test_every_angle_bracket_in_the_output_belongs_to_a_tag_the_converter_wrote(source):
    # Each start tag has one "<", and so does each end tag; <hr /> is the only tag without an end tag.
    output = convert(source)
    tags = inspect(output).tags
    assert output.count("<") == 2 * len(tags) - tags.count("hr")


def test_browser_scheme_helper_sees_through_whitespace_tricks():
    # Guards test_output_for_hostile_input...: the scheme check there must itself be able to fail.
    assert browser_scheme("java\tscript:alert(1)") == "javascript"
    assert browser_scheme(" \x01JavaScript:alert(1)") == "javascript"
    assert browser_scheme("/a/b:c") is None
    assert browser_scheme("&#106;avascript:alert(1)") is None



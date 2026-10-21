import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from mdhtml.inline import is_safe_url, render_inline


def test_special_characters_in_plain_text_are_escaped():
    assert render_inline("1 < 2 & \"x\" > 'y'") == "1 &lt; 2 &amp; &quot;x&quot; &gt; &#x27;y&#x27;"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("**bold**", "<strong>bold</strong>"),
        ("__bold__", "<strong>bold</strong>"),
        ("*it*", "<em>it</em>"),
        ("_it_", "<em>it</em>"),
        ("***both***", "<em><strong>both</strong></em>"),
        ("*a **b** c*", "<em>a <strong>b</strong> c</em>"),
        ("**a *b* c**", "<strong>a <em>b</em> c</strong>"),
        ("**Hello**, world", "<strong>Hello</strong>, world"),
        ("a*b*c", "a<em>b</em>c"),
    ],
)
def test_emphasis_forms(source, expected):
    assert render_inline(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # Cases where a run can both open and close: the "rule of three" decides who pairs with whom.
        ("*foo**bar*", "<em>foo**bar</em>"),
        ("*foo**bar**baz*", "<em>foo<strong>bar</strong>baz</em>"),
        ("foo***bar***baz", "foo<em><strong>bar</strong></em>baz"),
        ("_(foo)_", "<em>(foo)</em>"),
        ("foo_bar_", "foo_bar_"),
    ],
)
def test_emphasis_pairing_edge_cases(source, expected):
    assert render_inline(source) == expected


@pytest.mark.parametrize("source", ["snake_case_name", "a_b_c d_e", "2 * 3 * 4", "**", "x _ y _ z"])
def test_delimiters_that_cannot_open_or_close_stay_literal(source):
    assert render_inline(source) == source


def test_unmatched_delimiters_are_kept_as_text():
    assert render_inline("*foo") == "*foo"
    assert render_inline("foo**") == "foo**"
    assert render_inline("**foo*") == "*<em>foo</em>"


def test_a_matched_pair_blocks_overlapping_delimiters_inside_it():
    # CommonMark: the `*` pair closes first, so the `_` opened inside it can no longer pair with the later `_`.
    assert render_inline("*foo _bar* baz_") == "<em>foo _bar</em> baz_"


def test_many_closers_with_nothing_to_close_are_left_alone():
    # Also a regression guard: every closer used to rescan all earlier text, which made this input take seconds.
    text = "a* " * 5000
    assert render_inline(text) == text
    assert render_inline("a_ " * 5000) == "a_ " * 5000


def test_code_span_content_is_not_interpreted_and_is_escaped():
    assert render_inline("`*not em* <b>`") == "<code>*not em* &lt;b&gt;</code>"


def test_code_span_with_longer_fence_can_contain_a_backtick():
    assert render_inline("`` a`b ``") == "<code>a`b</code>"


def test_unclosed_backtick_is_literal_and_only_spaces_are_not_trimmed():
    assert render_inline("`abc") == "`abc"
    assert render_inline("` `") == "<code> </code>"


def test_backslash_escapes_make_punctuation_literal():
    assert render_inline(r"\*not italic\*") == "*not italic*"
    assert render_inline(r"\<b>") == "&lt;b&gt;"
    assert render_inline(r"back\slash") == r"back\slash"


def test_basic_link_with_title_and_formatted_label():
    assert render_inline("[Luvia](https://example.com)") == '<a href="https://example.com">Luvia</a>'
    assert render_inline('[x](http://a.b "A title")') == '<a href="http://a.b" title="A title">x</a>'
    assert render_inline("[**bold** text](/p)") == '<a href="/p"><strong>bold</strong> text</a>'


def test_link_destination_keeps_balanced_parentheses_and_escapes_ampersands():
    assert (
        render_inline("[w](https://en.wikipedia.org/wiki/Foo_(bar))")
        == '<a href="https://en.wikipedia.org/wiki/Foo_(bar)">w</a>'
    )
    assert render_inline("[q](/s?a=1&b=2)") == '<a href="/s?a=1&amp;b=2">q</a>'


def test_link_inside_emphasis():
    assert render_inline("*see [x](/y)*") == '<em>see <a href="/y">x</a></em>'


@pytest.mark.parametrize(
    "source",
    ["[just brackets]", "[a](b", "[a] (b)", "[a](b c)", "[a](b \"unterminated)", "![alt"],
)
def test_text_that_is_not_a_complete_link_is_output_verbatim(source):
    assert render_inline(source) == source.replace('"', "&quot;")


def test_brackets_inside_link_label_are_kept():
    assert render_inline("[a [b] c](/x)") == '<a href="/x">a [b] c</a>'


def test_anchors_never_nest():
    assert render_inline("[a [b](/inner) c](/outer)") == '<a href="/outer">a [b](/inner) c</a>'


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "  javascript:alert(1)",
        "java\tscript:alert(1)",
        "java\nscript:alert(1)",
        "\x01javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ],
)
def test_unsafe_url_schemes_are_rejected(url):
    assert is_safe_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        "http://a.b",
        "https://a.b/c?d=1#e",
        "HTTPS://A.B",
        "mailto:me@example.com",
        "/relative/path",
        "relative.html",
        "../up",
        "#section",
        "?q=1",
        "//cdn.example.com/x",
        "foo/bar:baz",
        "",
    ],
)
def test_safe_urls_are_accepted(url):
    assert is_safe_url(url) is True


def test_link_with_unsafe_scheme_keeps_label_text_but_drops_the_anchor():
    assert render_inline("[click **me**](javascript:alert(1))") == "click <strong>me</strong>"


def test_numeric_entity_cannot_smuggle_a_scheme():
    # "&" is escaped, so the browser sees the literal text "&#106;avascript:..." as a relative path.
    assert (
        render_inline("[x](&#106;avascript:alert(1))") == '<a href="&amp;#106;avascript:alert(1)">x</a>'
    )


def test_quotes_in_url_and_title_cannot_break_out_of_the_attribute():
    assert (
        render_inline('[x](http://a.b/"onmouseover="alert(1))')
        == '<a href="http://a.b/&quot;onmouseover=&quot;alert(1)">x</a>'
    )
    assert (
        render_inline(r'[x](/a "t\" onclick=\"y")')
        == '<a href="/a" title="t&quot; onclick=&quot;y">x</a>'
    )


def test_html_in_link_label_is_escaped():
    assert (
        render_inline("[<img src=x onerror=alert(1)>](/ok)")
        == '<a href="/ok">&lt;img src=x onerror=alert(1)&gt;</a>'
    )

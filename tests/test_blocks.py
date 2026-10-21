import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from mdhtml import MarkdownError, convert


def test_headings_one_to_six():
    assert convert("# One\n## Two\n###### Six") == "<h1>One</h1>\n<h2>Two</h2>\n<h6>Six</h6>\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("####### seven", "<p>####### seven</p>\n"),
        ("#hashtag", "<p>#hashtag</p>\n"),
        ("# Title ##", "<h1>Title</h1>\n"),
        ("## C#", "<h2>C#</h2>\n"),
        ("#", "<h1></h1>\n"),
        ("# *em* heading", "<h1><em>em</em> heading</h1>\n"),
        ("   # indented", "<h1>indented</h1>\n"),
    ],
)
def test_heading_edge_cases(source, expected):
    assert convert(source) == expected


def test_paragraph_lines_are_joined_and_blank_lines_separate_paragraphs():
    assert convert("line one\nline two\n\nsecond") == "<p>line one\nline two</p>\n<p>second</p>\n"
    assert convert("  a  \n  b  ") == "<p>a\nb</p>\n"


def test_fenced_code_is_verbatim_and_escaped_with_language_class():
    source = '```python\ndef f():\n    return "<b>"  # & more\n```'
    assert convert(source) == (
        '<pre><code class="language-python">def f():\n'
        "    return &quot;&lt;b&gt;&quot;  # &amp; more\n"
        "</code></pre>\n"
    )


def test_markdown_inside_a_code_block_is_not_interpreted_and_blank_lines_survive():
    assert convert("```\n# not heading\n**not bold**\n\nlast\n```") == (
        "<pre><code># not heading\n**not bold**\n\nlast\n</code></pre>\n"
    )


def test_fence_variants():
    assert convert("~~~\nx\n~~~") == "<pre><code>x\n</code></pre>\n"
    assert convert("```\n```") == "<pre><code></code></pre>\n"
    # A closing fence must be at least as long as the opening one.
    assert convert("````\n```\n````") == "<pre><code>```\n</code></pre>\n"
    # A tilde fence is not closed by backticks.
    assert convert("~~~\na\n```\nb\n~~~") == "<pre><code>a\n```\nb\n</code></pre>\n"
    # Extra words after the language are ignored.
    assert convert("```js title=x\n1\n```") == '<pre><code class="language-js">1\n</code></pre>\n'


def test_unclosed_fence_runs_to_the_end_of_the_document():
    assert convert("```\ncode\nmore") == "<pre><code>code\nmore\n</code></pre>\n"


def test_opening_fence_indentation_is_removed_from_code_lines():
    assert convert("  ```\n  code\n   more\n  ```") == "<pre><code>code\n more\n</code></pre>\n"


def test_language_name_is_escaped():
    assert convert("```<script>\nx\n```") == (
        '<pre><code class="language-&lt;script&gt;">x\n</code></pre>\n'
    )


def test_backticks_on_one_line_are_an_inline_span_not_a_fence():
    assert convert("```a`b```") == "<p><code>a`b</code></p>\n"


def test_code_span_may_cross_a_line_break_which_becomes_a_space():
    assert convert("see `a\nb` here") == "<p>see <code>a b</code> here</p>\n"


@pytest.mark.parametrize("source", ["---", "***", "___", "- - -", "* * *", " ***", "-----------"])
def test_thematic_breaks(source):
    assert convert(source) == "<hr />\n"


def test_two_marks_are_not_a_rule_and_a_rule_splits_paragraphs():
    assert convert("--") == "<p>--</p>\n"
    assert convert("**") == "<p>**</p>\n"
    assert convert("a\n\n---\n\nb") == "<p>a</p>\n<hr />\n<p>b</p>\n"
    assert convert("a\n---") == "<p>a</p>\n<hr />\n"


def test_blockquote_joins_lines_and_accepts_lazy_continuation():
    expected = "<blockquote>\n<p>one\ntwo</p>\n</blockquote>\n"
    assert convert("> one\n> two") == expected
    assert convert("> one\ntwo") == expected
    assert convert(">no space") == "<blockquote>\n<p>no space</p>\n</blockquote>\n"


def test_nested_blockquote():
    assert convert("> a\n>\n> > b") == (
        "<blockquote>\n<p>a</p>\n<blockquote>\n<p>b</p>\n</blockquote>\n</blockquote>\n"
    )


def test_blockquote_holds_other_blocks():
    assert convert("> - x\n> - y") == "<blockquote>\n<ul>\n<li>x</li>\n<li>y</li>\n</ul>\n</blockquote>\n"
    assert convert("> # T") == "<blockquote>\n<h1>T</h1>\n</blockquote>\n"


def test_blank_line_ends_a_blockquote_and_a_heading_cannot_be_continued_lazily():
    assert convert("> a\n\n> b") == "<blockquote>\n<p>a</p>\n</blockquote>\n<blockquote>\n<p>b</p>\n</blockquote>\n"
    assert convert("> # T\nafter") == "<blockquote>\n<h1>T</h1>\n</blockquote>\n<p>after</p>\n"


def test_empty_blockquote():
    assert convert(">") == "<blockquote>\n</blockquote>\n"


def test_unordered_list_and_marker_change_starts_a_new_list():
    assert convert("- a\n- b\n- c") == "<ul>\n<li>a</li>\n<li>b</li>\n<li>c</li>\n</ul>\n"
    assert convert("* a\n+ b") == "<ul>\n<li>a</li>\n</ul>\n<ul>\n<li>b</li>\n</ul>\n"


def test_ordered_lists_keep_their_start_number_and_delimiter_change_splits():
    assert convert("1. a\n2. b") == "<ol>\n<li>a</li>\n<li>b</li>\n</ol>\n"
    assert convert("3. a\n4. b") == '<ol start="3">\n<li>a</li>\n<li>b</li>\n</ol>\n'
    assert convert("1) a\n2) b") == "<ol>\n<li>a</li>\n<li>b</li>\n</ol>\n"
    assert convert("1. a\n1) b") == "<ol>\n<li>a</li>\n</ol>\n<ol>\n<li>b</li>\n</ol>\n"


def test_nested_list():
    assert convert("- a\n  - b\n  - c\n- d") == (
        "<ul>\n<li>a\n<ul>\n<li>b</li>\n<li>c</li>\n</ul>\n</li>\n<li>d</li>\n</ul>\n"
    )


def test_ordered_list_nested_in_bullet_list_and_back():
    assert convert("- a\n  1. x\n  2. y") == (
        "<ul>\n<li>a\n<ol>\n<li>x</li>\n<li>y</li>\n</ol>\n</li>\n</ul>\n"
    )
    assert convert("1. a\n   - b") == "<ol>\n<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>\n</ol>\n"


def test_nested_item_must_align_with_the_parent_text():
    # "1. " puts the text at column 3, so a two-space indent is not enough to nest.
    assert convert("1. a\n  - b") == "<ol>\n<li>a</li>\n</ol>\n<ul>\n<li>b</li>\n</ul>\n"


def test_leading_tab_counts_as_four_columns_of_nesting():
    assert convert("- a\n\t- b") == "<ul>\n<li>a\n<ul>\n<li>b</li>\n</ul>\n</li>\n</ul>\n"
    # With a blank line in between, nothing but the tab's width can attach "b" to the item.
    assert convert("- a\n\n\t- b") == "<ul>\n<li>\n<p>a</p>\n<ul>\n<li>b</li>\n</ul>\n</li>\n</ul>\n"


def test_blank_line_between_items_makes_the_list_loose():
    assert convert("- a\n\n- b") == "<ul>\n<li>\n<p>a</p>\n</li>\n<li>\n<p>b</p>\n</li>\n</ul>\n"


def test_blank_line_inside_an_item_makes_the_list_loose():
    assert convert("- a\n\n  b\n- c") == (
        "<ul>\n<li>\n<p>a</p>\n<p>b</p>\n</li>\n<li>\n<p>c</p>\n</li>\n</ul>\n"
    )


def test_blank_line_inside_a_nested_list_does_not_loosen_the_outer_list():
    assert convert("- a\n  - b\n\n  - c\n- d") == (
        "<ul>\n"
        "<li>a\n<ul>\n<li>\n<p>b</p>\n</li>\n<li>\n<p>c</p>\n</li>\n</ul>\n</li>\n"
        "<li>d</li>\n"
        "</ul>\n"
    )


def test_code_block_inside_a_list_item():
    assert convert("- item\n\n  ```\n  code\n  ```\n- next") == (
        "<ul>\n<li>\n<p>item</p>\n<pre><code>code\n</code></pre>\n</li>\n<li>\n<p>next</p>\n</li>\n</ul>\n"
    )


def test_list_item_text_can_continue_on_the_next_line_without_indentation():
    assert convert("- a\nb\n- c") == "<ul>\n<li>a\nb</li>\n<li>c</li>\n</ul>\n"


def test_unindented_line_after_code_in_an_item_ends_the_item_instead_of_joining_the_code():
    assert convert("- a\n  ```\n  code\ntext") == (
        "<ul>\n<li>a\n<pre><code>code\n</code></pre>\n</li>\n</ul>\n<p>text</p>\n"
    )


def test_list_interrupts_a_paragraph_but_a_year_at_line_start_does_not():
    assert convert("text\n- a\n- b") == "<p>text</p>\n<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n"
    assert convert("text\n1. a") == "<p>text</p>\n<ol>\n<li>a</li>\n</ol>\n"
    assert convert("in the year\n1990. nice") == "<p>in the year\n1990. nice</p>\n"


def test_empty_list_item():
    assert convert("-\n- b") == "<ul>\n<li></li>\n<li>b</li>\n</ul>\n"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("-not a list", "<p>-not a list</p>\n"),
        ("*emphasis* start", "<p><em>emphasis</em> start</p>\n"),
        ("1234567890. too many digits", "<p>1234567890. too many digits</p>\n"),
    ],
)
def test_marker_lookalikes_are_paragraphs(source, expected):
    assert convert(source) == expected


def test_item_with_inline_formatting():
    assert convert("- **bold** and `code`") == "<ul>\n<li><strong>bold</strong> and <code>code</code></li>\n</ul>\n"


def test_table_with_alignment():
    source = "| Name | Qty |\n|:-----|----:|\n| Apple | 3 |\n| Pear  | 12 |"
    assert convert(source) == (
        "<table>\n<thead>\n"
        '<tr><th style="text-align: left">Name</th><th style="text-align: right">Qty</th></tr>\n'
        "</thead>\n<tbody>\n"
        '<tr><td style="text-align: left">Apple</td><td style="text-align: right">3</td></tr>\n'
        '<tr><td style="text-align: left">Pear</td><td style="text-align: right">12</td></tr>\n'
        "</tbody>\n</table>\n"
    )


def test_table_center_alignment_and_default_alignment():
    assert convert("| a | b |\n|:-:|---|\n| 1 | 2 |") == (
        "<table>\n<thead>\n"
        '<tr><th style="text-align: center">a</th><th>b</th></tr>\n'
        "</thead>\n<tbody>\n"
        '<tr><td style="text-align: center">1</td><td>2</td></tr>\n'
        "</tbody>\n</table>\n"
    )


def test_table_without_outer_pipes():
    assert convert("a | b\n--|--\n1 | 2") == (
        "<table>\n<thead>\n<tr><th>a</th><th>b</th></tr>\n</thead>\n"
        "<tbody>\n<tr><td>1</td><td>2</td></tr>\n</tbody>\n</table>\n"
    )


def test_escaped_pipe_stays_inside_its_cell():
    assert convert("| a |\n|---|\n| x \\| y |") == (
        "<table>\n<thead>\n<tr><th>a</th></tr>\n</thead>\n"
        "<tbody>\n<tr><td>x | y</td></tr>\n</tbody>\n</table>\n"
    )


def test_ragged_rows_are_padded_and_truncated_to_the_header_width():
    assert convert("| a | b |\n|---|---|\n| 1 |\n| 1 | 2 | 3 |") == (
        "<table>\n<thead>\n<tr><th>a</th><th>b</th></tr>\n</thead>\n<tbody>\n"
        "<tr><td>1</td><td></td></tr>\n"
        "<tr><td>1</td><td>2</td></tr>\n"
        "</tbody>\n</table>\n"
    )


def test_table_cells_support_inline_markup_and_escape_html():
    assert convert("| *a* | <b> |\n|--|--|\n| **c** | [d](/e) |") == (
        "<table>\n<thead>\n<tr><th><em>a</em></th><th>&lt;b&gt;</th></tr>\n</thead>\n"
        '<tbody>\n<tr><td><strong>c</strong></td><td><a href="/e">d</a></td></tr>\n</tbody>\n</table>\n'
    )


def test_header_only_table_has_no_tbody():
    assert convert("| a |\n|---|") == "<table>\n<thead>\n<tr><th>a</th></tr>\n</thead>\n</table>\n"


def test_table_ends_at_a_blank_line_and_can_interrupt_a_paragraph():
    assert convert("| a |\n|---|\n| 1 |\n\nafter") == (
        "<table>\n<thead>\n<tr><th>a</th></tr>\n</thead>\n<tbody>\n<tr><td>1</td></tr>\n</tbody>\n</table>\n"
        "<p>after</p>\n"
    )
    assert convert("intro\n| a | b |\n|---|---|\n| 1 | 2 |").startswith("<p>intro</p>\n<table>\n")


@pytest.mark.parametrize(
    "source",
    [
        "| a | b |\n|---|\ntext",  # delimiter row has a different width
        "just text | with a pipe\nnext line",  # no delimiter row
        "a\n---",  # a rule, not a one-column table
    ],
)
def test_lookalikes_are_not_tables(source):
    assert "<table>" not in convert(source)


def test_empty_and_blank_documents_render_nothing():
    assert convert("") == ""
    assert convert("\n\n  \n\t\n") == ""


def test_windows_and_old_mac_line_endings():
    assert convert("a\r\n\r\nb\r\n") == "<p>a</p>\n<p>b</p>\n"
    assert convert("# T\r\r- x") == "<h1>T</h1>\n<ul>\n<li>x</li>\n</ul>\n"


def test_nul_character_is_replaced():
    assert convert("a\0b") == "<p>a�b</p>\n"


@pytest.mark.parametrize("bad", [b"# bytes", None, 42, ["# list"]])
def test_non_string_input_raises_type_error(bad):
    with pytest.raises(TypeError, match="must be str"):
        convert(bad)


def test_nesting_limit_is_enforced_for_quotes_and_lists():
    assert convert(">" * 32 + " x").count("<blockquote>") == 32
    with pytest.raises(MarkdownError, match="nested deeper than 32"):
        convert(">" * 33 + " x")
    with pytest.raises(MarkdownError, match="nested deeper"):
        convert("- " * 100 + "x")


def test_document_with_many_block_types():
    source = (
        "# Release notes\n"
        "\n"
        "Version **2.0** adds _tables_ and `inline code`.\n"
        "\n"
        "> Note: breaking change.\n"
        "\n"
        "1. Install\n"
        "2. Configure\n"
        "   - set `PATH`\n"
        "   - restart\n"
        "\n"
        "---\n"
        "\n"
        "| Key | Value |\n"
        "|-----|-------|\n"
        "| a   | 1     |\n"
    )
    assert convert(source) == (
        "<h1>Release notes</h1>\n"
        "<p>Version <strong>2.0</strong> adds <em>tables</em> and <code>inline code</code>.</p>\n"
        "<blockquote>\n<p>Note: breaking change.</p>\n</blockquote>\n"
        "<ol>\n<li>Install</li>\n<li>Configure\n<ul>\n<li>set <code>PATH</code></li>\n<li>restart</li>\n</ul>\n</li>\n</ol>\n"
        "<hr />\n"
        "<table>\n<thead>\n<tr><th>Key</th><th>Value</th></tr>\n</thead>\n"
        "<tbody>\n<tr><td>a</td><td>1</td></tr>\n</tbody>\n</table>\n"
    )

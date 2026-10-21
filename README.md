# mdhtml

A Markdown-to-HTML converter written from scratch in Python with no third-party libraries. It handles the everyday subset of Markdown (headings, emphasis, code, links, lists, quotes, rules and pipe tables) and treats the input as untrusted: raw HTML and `javascript:` links cannot inject anything into the output. A small command line converts a file and prints the HTML on stdout.

## Interesting engineering

- **Parse, then render.** Block structure is parsed into a small tree of dataclasses and rendered separately. Containers (block quotes, list items) strip their own prefix and re-parse the remaining lines, so any nesting works through plain recursion.
- **Emphasis without regex hacks.** `*`/`_` runs are resolved with a CommonMark-style delimiter algorithm (flanking rules and the "rule of three"), so `snake_case_name` stays untouched, `***x***` nests as `<em><strong>`, and `*foo**bar*` pairs the way CommonMark does.
- **Injection safety by construction.** Every piece of input text is HTML-escaped; the only markup emitted is a fixed set of tags. Link targets must be relative or `http`, `https` or `mailto`, and the tabs, newlines and control characters that browsers skip are removed before the scheme is checked. A link with an unsafe target keeps its text and loses the anchor.
- **Tests that re-parse the output.** The security tests feed hostile Markdown through the converter, parse the HTML again with `html.parser`, and assert that only the allowed tags and attributes appear and every `href` has a safe scheme.
- **Lists done properly.** Tight and loose lists are decided from blank lines between sibling blocks (a blank line inside a nested list does not loosen the outer one), unindented lines can continue an item's text lazily, and the parser tracks open code fences so such a line is never swallowed into code.

## Usage

Command line (reads UTF-8, writes UTF-8 to stdout, `-` reads standard input):

```
python -m mdhtml notes.md > notes.html
```

From Python:

```python
from mdhtml import convert

convert("Buy **fresh** bread and [jam](https://example.com).\n")
# '<p>Buy <strong>fresh</strong> bread and <a href="https://example.com">jam</a>.</p>\n'

convert("<script>alert(1)</script>")
# '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>\n'
```

Errors: non-`str` input raises `TypeError`; quotes or lists nested deeper than 32 levels raise `mdhtml.MarkdownError`. The command line prints `mdhtml: <message>` to stderr and exits with status 1 for an unreadable file, invalid UTF-8 or over-nested input.

## Supported syntax

Headings `#` to `######`, paragraphs, `**bold**`/`__bold__`, `*italic*`/`_italic_`, `` `inline code` ``, fenced code blocks (``` or `~~~`, optional language), `[links](url "title")`, unordered (`-`, `+`, `*`) and ordered (`1.`, `1)`) lists with nesting, `>` block quotes, horizontal rules, pipe tables with `:--`, `:-:`, `--:` alignment, and backslash escapes.

## Limitations

- Not supported: setext headings (`===` / `---` underlines), indented code blocks, images, reference-style links, autolinks like `<https://...>`, `<url>` link destinations, hard line breaks, strikethrough, task lists, footnotes. Raw HTML is never passed through; it is shown as text on purpose.
- A nested list item must be indented to the column where the parent item's text starts (CommonMark's rule): three spaces under `1. `, two under `- `.
- Leading tabs are turned into four spaces everywhere, including inside fenced code blocks.
- An unclosed code fence runs to the end of the document. A link inside link text is left as literal text so anchors never nest.
- Link schemes are an allowlist, so a legitimate `ftp:` link is rendered as plain text.
- The behaviour follows CommonMark on the cases covered by the tests, but the converter has not been checked against the full CommonMark specification suite.
- Input with many thousands of unmatched `[` characters is slow (quadratic time), because each one scans ahead for its closing bracket. Emphasis resolution does not have this problem.

## Running the tests

```
python -m pytest -q
```

The tests need only `pytest`; they use no network, clock or randomness.

Built with AI coding assistance.

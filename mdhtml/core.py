"""Render parsed block nodes to HTML and expose the one-call ``convert`` API."""

from __future__ import annotations

from collections.abc import Sequence

from .blocks import CodeBlock, Heading, ListBlock, Node, Paragraph, Quote, Rule, Table, parse
from .inline import escape, render_inline

_ALIGN_STYLE = {
    None: "",
    "left": ' style="text-align: left"',
    "center": ' style="text-align: center"',
    "right": ' style="text-align: right"',
}


def convert(markdown: str) -> str:
    """Convert Markdown text to an HTML fragment.

    All text from the input is HTML-escaped, so raw HTML in the source is shown
    as text and links to schemes other than http, https and mailto lose their
    anchor. Raises TypeError for non-str input and MarkdownError for input that
    nests quotes or lists absurdly deep.
    """
    return render_document(parse(markdown))


def render_document(nodes: Sequence[Node]) -> str:
    """Join block HTML with newlines; an empty document renders as an empty string."""
    if not nodes:
        return ""
    return "\n".join(_render_node(node) for node in nodes) + "\n"


def _render_node(node: Node) -> str:
    match node:
        case Heading(level=level, text=text):
            return f"<h{level}>{render_inline(text)}</h{level}>"
        case Paragraph(text=text):
            return f"<p>{render_inline(text)}</p>"
        case CodeBlock(language=language, code=code):
            language_attr = f' class="language-{escape(language)}"' if language else ""
            return f"<pre><code{language_attr}>{escape(code)}</code></pre>"
        case Rule():
            return "<hr />"
        case Quote(children=children):
            return f"<blockquote>\n{render_document(children)}</blockquote>"
        case ListBlock():
            return _render_list(node)
        case Table():
            return _render_table(node)


def _render_list(block: ListBlock) -> str:
    tag = "ol" if block.ordered else "ul"
    open_tag = f'<ol start="{block.start}">' if block.ordered and block.start != 1 else f"<{tag}>"
    items = [_render_item(item, block.tight) for item in block.items]
    return "\n".join([open_tag, *items, f"</{tag}>"])


def _render_item(children: Sequence[Node], tight: bool) -> str:
    if not children:
        return "<li></li>"
    if not tight:
        return f"<li>\n{render_document(children)}</li>"
    # Tight items put paragraph text directly inside <li>; other blocks sit on their own lines.
    inner = "".join(
        render_inline(child.text) if isinstance(child, Paragraph) else f"\n{_render_node(child)}\n"
        for child in children
    )
    return f"<li>{inner}</li>"


def _render_table(table: Table) -> str:
    def row(tag: str, cells: Sequence[str]) -> str:
        rendered = "".join(
            f"<{tag}{_ALIGN_STYLE[align]}>{render_inline(cell)}</{tag}>"
            for cell, align in zip(cells, table.aligns)
        )
        return f"<tr>{rendered}</tr>"

    lines = ["<table>", "<thead>", row("th", table.header), "</thead>"]
    if table.rows:
        lines += ["<tbody>", *(row("td", cells) for cells in table.rows), "</tbody>"]
    lines.append("</table>")
    return "\n".join(lines)

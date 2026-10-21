"""Block-level parsing: Markdown text -> a tree of block nodes.

Containers (block quotes, list items) are handled the way CommonMark does it
in spirit: strip the container's prefix from its lines, then parse those lines
again as a document of their own. That keeps each block type small and makes
arbitrary nesting fall out of recursion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import MarkdownError

# Each level of quote or list nesting costs a few Python frames; this keeps
# hostile input such as thousands of ">" characters from exhausting the stack.
MAX_NESTING_DEPTH = 32

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_ATX = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*))?$")
_ATX_CLOSING = re.compile(r"(?:^|[ \t]+)#+$")
_RULE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE = re.compile(r"^ {0,3}> ?(.*)$")
_FENCE_OPEN = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*(.*?)[ \t]*$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*$")
_LIST_MARKER = re.compile(r"^( {0,3})([-+*]|[0-9]{1,9}[.)])(?:([ \t]+)(.*))?$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_DELIMITER_CELL = re.compile(r":?-+:?")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str


@dataclass(frozen=True)
class Paragraph:
    text: str


@dataclass(frozen=True)
class CodeBlock:
    language: str
    code: str


@dataclass(frozen=True)
class Rule:
    pass


@dataclass(frozen=True)
class Quote:
    children: tuple[Node, ...]


@dataclass(frozen=True)
class ListBlock:
    ordered: bool
    start: int
    items: tuple[tuple[Node, ...], ...]
    tight: bool  # tight lists render item text without <p> wrappers


@dataclass(frozen=True)
class Table:
    header: tuple[str, ...]
    aligns: tuple[str | None, ...]
    rows: tuple[tuple[str, ...], ...]


Node = Heading | Paragraph | CodeBlock | Rule | Quote | ListBlock | Table


@dataclass(frozen=True)
class _Fence:
    indent: int
    char: str
    length: int
    info: str


@dataclass(frozen=True)
class _Marker:
    ordered: bool
    delimiter: str  # the bullet character, or "." / ")" for ordered lists
    number: int
    content_col: int  # column where item text starts; continuation lines must reach it
    text: str  # item text on the marker's own line


def parse(text: str) -> list[Node]:
    """Parse a Markdown document into block nodes.

    Raises TypeError for non-str input and MarkdownError when quotes or lists
    are nested more than MAX_NESTING_DEPTH levels.
    """
    if not isinstance(text, str):
        raise TypeError(f"markdown source must be str, not {type(text).__name__}")
    lines = [_expand_leading_tabs(line) for line in _LINE_BREAK.split(text.replace("\0", "�"))]
    return _parse_blocks(lines, 0)[0]


def _expand_leading_tabs(line: str) -> str:
    """Turn indentation tabs into spaces so nesting can be measured in columns."""
    body = line.lstrip(" \t")
    return line[: len(line) - len(body)].expandtabs(4) + body


def _parse_blocks(lines: list[str], depth: int) -> tuple[list[Node], bool]:
    """Parse lines into sibling blocks.

    The flag is True when a blank line separates two sibling blocks, which is
    what makes a list item (and so its list) "loose".
    """
    if depth > MAX_NESTING_DEPTH:
        raise MarkdownError(f"quotes and lists are nested deeper than {MAX_NESTING_DEPTH} levels")
    nodes: list[Node] = []
    spaced = False
    blank_seen = False
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            blank_seen = True
            i += 1
            continue
        node, i = _parse_block(lines, i, depth)
        if blank_seen and nodes:
            spaced = True
        blank_seen = False
        nodes.append(node)
    return nodes, spaced


def _parse_block(lines: list[str], i: int, depth: int) -> tuple[Node, int]:
    line = lines[i]
    fence = _open_fence(line)
    if fence is not None:
        return _parse_fence(lines, i, fence)
    heading = _ATX.match(line)
    if heading is not None:
        text = _ATX_CLOSING.sub("", (heading.group(2) or "").strip(), count=1).strip()
        return Heading(len(heading.group(1)), text), i + 1
    if _RULE.match(line):
        return Rule(), i + 1
    if _QUOTE.match(line):
        return _parse_quote(lines, i, depth)
    if _parse_marker(line) is not None:
        return _parse_list(lines, i, depth)
    if _is_table_start(lines, i):
        return _parse_table(lines, i)
    return _parse_paragraph(lines, i)


def _parse_paragraph(lines: list[str], i: int) -> tuple[Paragraph, int]:
    start = i
    i += 1
    while i < len(lines) and not _interrupts_paragraph(lines, i):
        i += 1
    return Paragraph("\n".join(line.strip() for line in lines[start:i])), i


def _starts_block(line: str) -> bool:
    """True if the line opens a fence, heading, rule, quote or list on its own."""
    return (
        _open_fence(line) is not None
        or _ATX.match(line) is not None
        or _RULE.match(line) is not None
        or _QUOTE.match(line) is not None
        or _parse_marker(line) is not None
    )


def _interrupts_paragraph(lines: list[str], i: int) -> bool:
    """True if lines[i] cannot be a continuation of the paragraph above it.

    A list may only interrupt a paragraph with a non-empty item, and an ordered
    list only when it starts at 1, so that a wrapped "... in" / "1990. It ..."
    stays ordinary text.
    """
    line = lines[i]
    if not line.strip():
        return True
    marker = _parse_marker(line)
    if marker is not None:
        return bool(marker.text.strip()) and (not marker.ordered or marker.number == 1)
    return _starts_block(line) or _is_table_start(lines, i)


def _is_lazy_continuation(lines: list[str], i: int, previous: str) -> bool:
    """True if lines[i], although it lacks its container's prefix, continues the paragraph ``previous`` ends.

    Unlike a top-level paragraph, any list marker ends the continuation here:
    the paragraph belongs to the container that the marker line just left.
    """
    line = lines[i]
    return (
        bool(previous.strip())
        and bool(line.strip())
        and not _starts_block(previous)
        and not _starts_block(line)
        and not _is_table_start(lines, i)
    )


# --- fenced code -----------------------------------------------------------


def _open_fence(line: str) -> _Fence | None:
    match = _FENCE_OPEN.match(line)
    if match is None:
        return None
    marker, info = match.group(2), match.group(3)
    if marker[0] == "`" and "`" in info:  # "```code```" is an inline span, not a fence
        return None
    return _Fence(len(match.group(1)), marker[0], len(marker), info)


def _closes_fence(line: str, fence: _Fence) -> bool:
    match = _FENCE_CLOSE.match(line)
    return match is not None and match.group(1)[0] == fence.char and len(match.group(1)) >= fence.length


def _track_fence(fence: _Fence | None, line: str) -> _Fence | None:
    """Fence state after ``line``; lets a container know whether it is inside code."""
    if fence is None:
        return _open_fence(line)
    return None if _closes_fence(line, fence) else fence


def _parse_fence(lines: list[str], i: int, fence: _Fence) -> tuple[CodeBlock, int]:
    code: list[str] = []
    i += 1
    while i < len(lines):
        if _closes_fence(lines[i], fence):
            i += 1
            break
        code.append(_strip_indent(lines[i], fence.indent))
        i += 1
    words = fence.info.split()
    return CodeBlock(words[0] if words else "", "".join(line + "\n" for line in code)), i


def _strip_indent(line: str, width: int) -> str:
    """Remove up to ``width`` leading spaces (the opening fence's own indentation)."""
    return line[min(width, len(line) - len(line.lstrip(" "))) :]


# --- block quotes ----------------------------------------------------------


def _parse_quote(lines: list[str], i: int, depth: int) -> tuple[Quote, int]:
    inner: list[str] = []
    fence: _Fence | None = None
    while i < len(lines):
        match = _QUOTE.match(lines[i])
        if match is not None:
            content = match.group(1)
        elif inner and fence is None and _is_lazy_continuation(lines, i, inner[-1]):
            content = lines[i].strip()
        else:
            break
        fence = _track_fence(fence, content)
        inner.append(content)
        i += 1
    children, _ = _parse_blocks(inner, depth + 1)
    return Quote(tuple(children)), i


# --- lists -----------------------------------------------------------------


def _parse_marker(line: str) -> _Marker | None:
    match = _LIST_MARKER.match(line)
    if match is None:
        return None
    indent, token, gap, rest = match.groups()
    gap, rest = gap or "", rest or ""
    if not rest.strip():
        width, rest = 1, ""
    else:
        width = len(gap) if len(gap) <= 4 else 1  # five or more spaces: text starts after one
        rest = gap[width:] + rest
    ordered = token[-1] in ".)"
    return _Marker(
        ordered=ordered,
        delimiter=token[-1],
        number=int(token[:-1]) if ordered else 0,
        content_col=len(indent) + len(token) + width,
        text=rest,
    )


def _skip_blank(lines: list[str], i: int) -> int:
    while i < len(lines) and not lines[i].strip():
        i += 1
    return i


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_list(lines: list[str], i: int, depth: int) -> tuple[ListBlock, int]:
    first = _parse_marker(lines[i])
    items: list[tuple[Node, ...]] = []
    loose = False
    while True:
        marker = _parse_marker(lines[i])
        item_lines, i = _collect_item(lines, i, marker)
        children, spaced = _parse_blocks(item_lines, depth + 1)
        items.append(tuple(children))
        loose = loose or spaced
        following = _skip_blank(lines, i)
        if following >= len(lines):
            break
        next_marker = _parse_marker(lines[following])
        if (
            next_marker is None
            or next_marker.ordered != first.ordered
            or next_marker.delimiter != first.delimiter
            or _RULE.match(lines[following])
        ):
            break
        if following > i:  # a blank line between two items
            loose = True
        i = following
    return ListBlock(first.ordered, first.number, tuple(items), not loose), i


def _collect_item(lines: list[str], i: int, marker: _Marker) -> tuple[list[str], int]:
    """Gather the lines of one list item, with the item's indentation removed."""
    item = [marker.text]
    fence = _open_fence(marker.text)
    i += 1
    while i < len(lines):
        following = _skip_blank(lines, i)
        if following >= len(lines):
            break
        line = lines[following]
        if _indent(line) >= marker.content_col:
            item.extend([""] * (following - i))  # blank lines kept only if the item goes on
            content = line[marker.content_col :]
        elif following == i and fence is None and _is_lazy_continuation(lines, following, item[-1]):
            content = line.strip()
        else:
            break
        fence = _track_fence(fence, content)
        item.append(content)
        i = following + 1
    return item, i


# --- tables ----------------------------------------------------------------


def _split_row(line: str) -> list[str]:
    """Split a table row into cells; ``\\|`` is a literal pipe, not a separator."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        text = text[:-1]
    return [cell.replace("\\|", "|").strip() for cell in _UNESCAPED_PIPE.split(text)]


def _parse_delimiter_row(line: str) -> tuple[str | None, ...] | None:
    """Alignments from a ``|---|:-:|`` row, or None if the line is not one."""
    if "|" not in line:
        return None
    cells = _split_row(line)
    if not all(_DELIMITER_CELL.fullmatch(cell) for cell in cells):
        return None
    return tuple(_alignment(cell) for cell in cells)


def _alignment(cell: str) -> str | None:
    if cell.startswith(":") and cell.endswith(":"):
        return "center"
    if cell.startswith(":"):
        return "left"
    if cell.endswith(":"):
        return "right"
    return None


def _is_table_start(lines: list[str], i: int) -> bool:
    """A table is a pipe-containing header row followed by a delimiter row of equal width."""
    if i + 1 >= len(lines) or "|" not in lines[i]:
        return False
    aligns = _parse_delimiter_row(lines[i + 1])
    return aligns is not None and len(aligns) == len(_split_row(lines[i]))


def _parse_table(lines: list[str], i: int) -> tuple[Table, int]:
    header = _split_row(lines[i])
    aligns = _parse_delimiter_row(lines[i + 1])
    i += 2
    rows: list[tuple[str, ...]] = []
    while i < len(lines) and lines[i].strip() and not _starts_block(lines[i]):
        cells = _split_row(lines[i])
        rows.append(tuple((cells + [""] * len(header))[: len(header)]))  # pad or cut to the header width
        i += 1
    return Table(tuple(header), aligns, tuple(rows)), i

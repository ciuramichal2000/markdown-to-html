"""Inline Markdown (emphasis, code spans, links) rendered straight to HTML.

Safety rests on one rule: every character taken from the input goes through
``escape`` before it reaches the output, and the only markup this module emits
is a fixed set of tags it writes itself. Link targets are additionally checked
against a scheme allowlist.
"""

from __future__ import annotations

import html
import re
import string
import unicodedata
from dataclasses import dataclass

SAFE_URL_SCHEMES = frozenset({"http", "https", "mailto"})

_PUNCTUATION = frozenset(string.punctuation)
_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*:")
_SPECIAL = re.compile(r"[\\`\[*_]")
_BACKTICK_RUN = re.compile(r"`+")


def escape(text: str) -> str:
    """Escape text for use in HTML element content and quoted attributes."""
    return html.escape(text, quote=True)


def is_safe_url(url: str) -> bool:
    """Return True if ``url`` is relative or uses an allowlisted scheme.

    Browsers ignore tabs, newlines and control characters inside a URL, so a
    tab in the middle of "javascript:" still runs. Those characters are removed
    before looking for the scheme, otherwise the check could be walked around.
    """
    visible = "".join(ch for ch in url if ch.isprintable() and not ch.isspace())
    scheme = _SCHEME.match(visible)
    return scheme is None or scheme.group()[:-1].lower() in SAFE_URL_SCHEMES


@dataclass
class _Delimiter:
    """A run of ``*`` or ``_`` that may still turn into emphasis tags."""

    char: str
    run: int  # length of the original run, needed for the "rule of three"
    length: int  # characters not yet consumed by a match
    can_open: bool
    can_close: bool
    open_tags: str = ""
    close_tags: str = ""


def render_inline(text: str, allow_links: bool = True) -> str:
    """Render one block's inline content to HTML.

    ``allow_links`` is False inside a link label so anchors never nest.
    """
    nodes: list[str | _Delimiter] = []
    pos = 0
    while pos < len(text):
        special = _SPECIAL.search(text, pos)
        if special is None:
            nodes.append(escape(text[pos:]))
            break
        if special.start() > pos:
            nodes.append(escape(text[pos : special.start()]))
        node, pos = _scan_special(text, special.start(), allow_links)
        nodes.append(node)
    _resolve_emphasis(nodes)
    return "".join(
        node if isinstance(node, str) else node.close_tags + node.char * node.length + node.open_tags
        for node in nodes
    )


def _scan_special(text: str, pos: int, allow_links: bool) -> tuple[str | _Delimiter, int]:
    """Handle the special character at ``pos``; return its output and the next position."""
    char = text[pos]
    if char == "\\":
        if pos + 1 < len(text) and text[pos + 1] in _PUNCTUATION:
            return escape(text[pos + 1]), pos + 2
        return "\\", pos + 1
    if char == "`":
        span = _code_span(text, pos)
        if span is not None:
            return span
        run_end = _BACKTICK_RUN.match(text, pos).end()
        return text[pos:run_end], run_end
    if char == "[":
        link = _link(text, pos) if allow_links else None
        return link if link is not None else ("[", pos + 1)
    end = pos
    while end < len(text) and text[end] == char:
        end += 1
    return _delimiter(text, pos, end), end


def _code_span(text: str, start: int) -> tuple[str, int] | None:
    """Parse a code span opened by the backtick run at ``start``.

    The span closes at the next run of exactly the same length, so a longer
    run lets the code itself contain backticks.
    """
    open_end = _BACKTICK_RUN.match(text, start).end()
    width = open_end - start
    for run in _BACKTICK_RUN.finditer(text, open_end):
        if run.end() - run.start() == width:
            code = text[open_end : run.start()].replace("\n", " ")
            if code.startswith(" ") and code.endswith(" ") and code.strip(" "):
                code = code[1:-1]
            return f"<code>{escape(code)}</code>", run.end()
    return None


def _closing_bracket(text: str, start: int) -> int | None:
    """Index of the ``]`` matching the ``[`` at ``start``, skipping escapes and code spans."""
    depth = 0
    pos = start
    while pos < len(text):
        char = text[pos]
        if char == "\\":
            pos += 2
            continue
        if char == "`":
            span = _code_span(text, pos)
            pos = span[1] if span is not None else _BACKTICK_RUN.match(text, pos).end()
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return None


def _link(text: str, start: int) -> tuple[str, int] | None:
    """Parse ``[label](target "title")``; an unsafe target keeps the label but drops the anchor."""
    close = _closing_bracket(text, start)
    if close is None or text[close + 1 : close + 2] != "(":
        return None
    target = _link_target(text, close + 2)
    if target is None:
        return None
    url, title, end = target
    label = render_inline(text[start + 1 : close], allow_links=False)
    if not is_safe_url(url):
        return label, end
    title_attr = "" if title is None else f' title="{escape(title)}"'
    return f'<a href="{escape(url)}"{title_attr}>{label}</a>', end


def _link_target(text: str, pos: int) -> tuple[str, str | None, int] | None:
    """Parse ``url "title")`` just after the opening parenthesis.

    Returns the url, the optional title and the index after the closing
    parenthesis, or None if the target is malformed.
    """
    pos = _skip_whitespace(text, pos)
    url: list[str] = []
    depth = 0
    while pos < len(text) and not text[pos].isspace():
        char = text[pos]
        if char == "\\" and text[pos + 1 : pos + 2] in _PUNCTUATION:
            url.append(text[pos + 1])
            pos += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        url.append(char)
        pos += 1
    pos = _skip_whitespace(text, pos)
    title = None
    if text[pos : pos + 1] in ('"', "'"):
        quote = text[pos]
        pos += 1
        chars: list[str] = []
        while pos < len(text) and text[pos] != quote:
            if text[pos] == "\\" and text[pos + 1 : pos + 2] in _PUNCTUATION:
                pos += 1
            chars.append(text[pos])
            pos += 1
        if pos >= len(text):
            return None
        title = "".join(chars)
        pos = _skip_whitespace(text, pos + 1)
    if text[pos : pos + 1] != ")":
        return None
    return "".join(url), title, pos + 1


def _skip_whitespace(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def _is_punctuation(char: str) -> bool:
    return unicodedata.category(char)[0] in ("P", "S")


def _delimiter(text: str, start: int, end: int) -> _Delimiter:
    """Classify the run ``text[start:end]`` as able to open and/or close emphasis.

    These are the CommonMark flanking rules: a run opens emphasis when it hugs
    the word that follows it and closes when it hugs the word before it.
    Underscores are stricter so that snake_case_names are left alone.
    """
    char = text[start]
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    left = not after.isspace() and (
        not _is_punctuation(after) or before.isspace() or _is_punctuation(before)
    )
    right = not before.isspace() and (
        not _is_punctuation(before) or after.isspace() or _is_punctuation(after)
    )
    if char == "*":
        can_open, can_close = left, right
    else:
        can_open = left and (not right or _is_punctuation(before))
        can_close = right and (not left or _is_punctuation(after))
    return _Delimiter(char, end - start, end - start, can_open, can_close)


def _resolve_emphasis(nodes: list[str | _Delimiter]) -> None:
    """Pair up delimiter runs, closest opener first, and record the tags on them.

    Tags are stored on the delimiters instead of rewriting the list, so a
    single run such as ``***`` can be consumed in several steps and still end
    up as properly nested ``<em><strong>`` tags.

    ``openers`` holds, in text order, only the runs that may still open
    emphasis. A closer searches that stack instead of every earlier node, so
    text full of closers that have nothing to close stays linear.
    """
    openers: list[_Delimiter] = []
    for node in nodes:
        if not isinstance(node, _Delimiter):
            continue
        closer = node
        while closer.can_close and closer.length > 0:
            position = _find_opener(openers, closer)
            if position is None:
                break
            opener = openers[position]
            used = 2 if opener.length >= 2 and closer.length >= 2 else 1
            tag = "strong" if used == 2 else "em"
            opener.length -= used
            closer.length -= used
            opener.open_tags = f"<{tag}>" + opener.open_tags
            closer.close_tags += f"</{tag}>"
            # Runs between a matched pair can no longer open or close anything.
            del openers[position + 1 :]
            if opener.length == 0:
                openers.pop()
        if closer.can_open and closer.length > 0:
            openers.append(closer)


def _find_opener(openers: list[_Delimiter], closer: _Delimiter) -> int | None:
    """Index in ``openers`` of the nearest run ``closer`` may pair with."""
    for position in range(len(openers) - 1, -1, -1):
        candidate = openers[position]
        if candidate.char != closer.char:
            continue
        # "Rule of three": a run that can both open and close does not pair with
        # a run when their original lengths sum to a multiple of 3, unless both
        # lengths are themselves multiples of 3. It keeps `*foo**bar*` sensible.
        mixed = candidate.can_close or closer.can_open
        if mixed and (candidate.run + closer.run) % 3 == 0 and not (
            candidate.run % 3 == 0 and closer.run % 3 == 0
        ):
            continue
        return position
    return None

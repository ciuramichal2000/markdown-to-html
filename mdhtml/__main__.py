"""Command line: ``python -m mdhtml FILE`` prints the HTML for FILE on stdout."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import BinaryIO, TextIO

from .core import convert
from .errors import MarkdownError


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the converter; returns the process exit status.

    The streams are parameters so tests can drive it without touching the real
    console. Output is written as UTF-8 bytes whatever the console encoding is,
    because the Windows default would fail on non-ASCII text.
    """
    parser = argparse.ArgumentParser(prog="mdhtml", description="Convert a Markdown file to HTML on stdout.")
    parser.add_argument("file", help="Markdown file to convert, or - to read standard input")
    args = parser.parse_args(argv)
    stdin = stdin if stdin is not None else sys.stdin.buffer
    stdout = stdout if stdout is not None else sys.stdout.buffer
    stderr = stderr if stderr is not None else sys.stderr

    try:
        result = convert(_read_source(args.file, stdin))
    except (OSError, MarkdownError) as error:
        print(f"mdhtml: {error}", file=stderr)
        return 1
    stdout.write(result.encode("utf-8"))
    stdout.flush()
    return 0


def _read_source(path: str, stdin: BinaryIO) -> str:
    """Read UTF-8 text from a file or stdin; a leading byte-order mark is dropped."""
    if path == "-":
        data = stdin.read()
    else:
        with open(path, "rb") as handle:
            data = handle.read()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        name = "standard input" if path == "-" else path
        raise MarkdownError(f"{name} is not valid UTF-8 text") from None


if __name__ == "__main__":
    raise SystemExit(main())

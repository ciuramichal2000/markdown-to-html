"""mdhtml: a small, dependency-free Markdown-to-HTML converter."""

from .core import convert
from .errors import MarkdownError

__all__ = ["convert", "MarkdownError"]

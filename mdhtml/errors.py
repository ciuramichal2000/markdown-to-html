"""Exceptions raised by mdhtml."""


class MarkdownError(ValueError):
    """The input is text, but it cannot be converted (for example, nested too deeply)."""

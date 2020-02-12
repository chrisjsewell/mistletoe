"""
Make mistletoe easier to import.
"""

__version__ = "0.7.2"
__all__ = [
    "html_renderer",
    "ast_renderer",
    "block_token",
    "block_tokenizer",
    "span_token",
    "span_tokenizer",
]

from mistletoe.block_token import Document  # noqa
from mistletoe.base_renderer import BaseRenderer  # noqa
from mistletoe.html_renderer import HTMLRenderer


def markdown(iterable, renderer=HTMLRenderer):
    """
    Output HTML with default settings.
    Enables inline and block-level HTML tags.
    """
    with renderer() as renderer:
        return renderer.render(Document(iterable))


def setup(app):
    """Initialize Sphinx extension."""
    from mistletoe.docutils_renderer import MystParser

    app.add_source_suffix(".md", "markdown")
    app.add_source_parser(MystParser)

    return {"version": __version__, "parallel_read_safe": True}

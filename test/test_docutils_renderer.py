from textwrap import dedent
from unittest import mock

import pytest
from mistletoe.docutils_renderer import DocutilsRenderer


@pytest.fixture
def renderer():
    renderer = DocutilsRenderer()
    renderer.render_inner = mock.Mock(return_value="inner")
    with renderer:
        yield renderer


def render_token(renderer, token_name, children=True, without_attrs=None, **kwargs):
    render_func = renderer.render_map[token_name]
    children = mock.MagicMock(spec=list) if children else None
    mock_token = mock.Mock(children=children, **kwargs)
    without_attrs = without_attrs or []
    for attr in without_attrs:
        delattr(mock_token, attr)
    render_func(mock_token)


def test_strong(renderer):
    render_token(renderer, "Strong")
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <strong>
    """
    )


def test_emphasis(renderer):
    render_token(renderer, "Emphasis")
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <emphasis>
    """
    )


def test_raw_text(renderer):
    render_token(renderer, "RawText", children=False, content="john & jane")
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        john & jane
    """
    )


def test_paragraph(renderer):
    render_token(renderer, "Paragraph", range=(0, 1))
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <paragraph>
    """
    )


def test_heading(renderer):
    render_token(renderer, "Heading", level=1, range=(0, 0))
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <section ids="id1" names="">
            <title>
    """
    )


def test_block_code(renderer):
    from mistletoe.block_token import tokenize

    renderer.render(tokenize(["```sh\n", "foo\n", "```\n"])[0])
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <literal_block language="sh" xml:space="preserve">
            foo
    """
    )


def test_block_code_no_language(renderer):
    from mistletoe.block_token import tokenize

    renderer.render(tokenize(["```\n", "foo\n", "```\n"])[0])
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <literal_block language="" xml:space="preserve">
            foo
    """
    )

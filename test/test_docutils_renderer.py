import json
import os
from textwrap import dedent, indent
from unittest import mock

import pytest

from mistletoe import Document
from mistletoe.block_token import tokenize
from mistletoe.span_token import tokenize_inner
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


def test_inline_code(renderer):
    renderer.render(tokenize_inner("`foo`")[0])
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <literal>
            foo
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

    renderer.render(tokenize(["```sh\n", "foo\n", "```\n"])[0])
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <literal_block language="sh" xml:space="preserve">
            foo
    """
    )


def test_block_code_no_language(renderer):

    renderer.render(tokenize(["```\n", "foo\n", "```\n"])[0])
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <literal_block language="" xml:space="preserve">
            foo
    """
    )


def test_image(renderer):
    render_token(renderer, "Image", src="src", title="title")
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <image alt="" uri="src">
    """
    )


def test_quote(renderer):
    render_token(renderer, "Quote", range=(0, 0))
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <block_quote>
    """
    )


def test_bullet_list(renderer):
    render_token(renderer, "List", start=None)
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <bullet_list>
    """
    )


def test_enumerated_list(renderer):
    render_token(renderer, "List", start=1)
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <enumerated_list>
    """
    )


def test_list_item(renderer):
    render_token(renderer, "ListItem")
    assert renderer.document.pformat() == dedent(
        """\
    <document source="">
        <list_item>
    """
    )


def test_full_run(renderer, file_regression):
    string = dedent(
        """\
        # header 1
        ## sub header 1

        a *b* **c** `abc` \\*

        ## sub header 2

        x y [a](http://www.xyz.com) z

        ---

        # header 2

        ```::python {a=1}
        a = 1
        ```

        > abc

        - a
        - b
            - c

        1. a
        2. b
            1. c

        """
    )

    renderer.render(Document(string))
    file_regression.check(renderer.document.pformat(), extension=".xml")


with open(
    os.path.join(os.path.dirname(__file__), "samples", "sphinx_directives.json"), "r"
) as fin:
    directives = json.load(fin)


@pytest.mark.parametrize(
    "directive",
    [
        d
        for d in directives
        if d["class"].startswith("docutils") and not d.get("sub_only", False)
        # todo add substitution definition directive and reference role
    ],
)
def test_docutils_directives(renderer, directive):
    """See https://docutils.sourceforge.io/docs/ref/rst/directives.html"""
    # TODO load and test sphinx directives/roles
    name = directive["name"]
    if name in ["role", "rst-class", "cssclass", "line-block"]:
        # TODO fix skips
        pytest.skip("awaiting fix")
    arguments = " ".join(directive["args"])
    renderer.render(
        tokenize(
            [
                "```{{{}}} {}\n".format(name, arguments),
                directive.get("content", "") + "\n",
                "```\n",
            ]
        )[0]
    )
    # print(
    #     repr(renderer.document.pformat()).replace(" " * 8, "    ").replace('"', '\\"')
    # )
    assert renderer.document.pformat() == (
        directive.get("doc_tag", '<document source="">')
        + "\n"
        + indent(directive["output"], "    ")
        + ("\n" if directive["output"] else "")
    )

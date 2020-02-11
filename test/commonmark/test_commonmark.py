import json
import os

import pytest

from mistletoe import Document
from mistletoe.html_renderer import HTMLRenderer
from mistletoe.latex_token import Math

with open(os.path.join(os.path.dirname(__file__), "commonmark.json"), "r") as fin:
    tests = json.load(fin)


@pytest.mark.parametrize("entry", tests)
def test_commonmark(entry):
    test_case = entry["markdown"].splitlines(keepends=True)
    with HTMLRenderer(Math) as renderer:
        output = renderer.render(Document(test_case))
    assert entry["html"] == output

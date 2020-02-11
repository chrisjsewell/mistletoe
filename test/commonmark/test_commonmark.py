import json
import os

import pytest

from mistletoe import markdown

with open(os.path.join(os.path.dirname(__file__), "commonmark.json"), "r") as fin:
    tests = json.load(fin)


@pytest.mark.parametrize("entry", tests)
def test_commonmark(entry):
    # result = run_test(entry, quiet=False)
    # if not result[0]:
    #     raise ValueError

    test_case = entry["markdown"].splitlines(keepends=True)
    output = markdown(test_case)
    assert entry["html"] == output

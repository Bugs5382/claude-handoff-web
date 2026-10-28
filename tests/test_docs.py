"""The docs are tested like code: every page file example in them is a valid handoff.page/v1 definition."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "template" / "_site"))

import schema  # noqa: E402

DOCS = [ROOT / "docs" / "page-types.md", ROOT / "example" / "guide" / "page-types.md", ROOT / "docs" / "quick-start.md"]


def examples():
    for doc in DOCS:
        for n, block in enumerate(re.findall(r"```json\n(.*?)```", doc.read_text(), re.S), 1):
            if '"schema": "handoff.page/v1"' in block:
                yield pytest.param(block, id=f"{doc.parent.name}/{doc.name}#{n}")


def full(definition):
    return dict(definition, rev=1, rounds=[{"round": 1, "build": None, "reset": None, "opened": "t", "closed": None,
                                            "openedBy": "created", "answers": {}}], thread={}, submissions=[])


@pytest.mark.parametrize("block", list(examples()))
def test_every_page_example_in_the_docs_is_valid(block):
    assert schema.validate(full(json.loads(block))) == []


def test_every_kind_has_an_example():
    kinds = {json.loads(b.values[0])["kind"] for b in examples()}
    assert kinds >= set(schema.KINDS)


def test_the_example_folder_holds_only_valid_page_files():
    files = sorted((ROOT / "example" / "demo").glob("*"))
    assert {f.suffix for f in files if f.is_file()} == {".json"}
    for f in files:
        if f.is_file():
            assert schema.validate(json.loads(f.read_text())) == [], f.name

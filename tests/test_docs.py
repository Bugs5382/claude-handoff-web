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


def test_the_template_claude_md_is_the_same_as_agents_md():
    assert (ROOT / "template" / "CLAUDE.md").read_text() == (ROOT / "template" / "AGENTS.md").read_text()


GUIDE = ROOT / "template" / "_site" / "GUIDE.md"
RULES = ROOT / "template" / "CLAUDE.md"


def elements():
    return re.findall(r"\w+", re.search(r"export \{ Answer,(.*?)\};", (ROOT / "web" / "src" / "index.tsx").read_text(), re.S).group(0))[1:]


@pytest.mark.parametrize("doc", [GUIDE, RULES])
def test_every_page_kind_and_item_type_is_covered(doc):
    text = doc.read_text()
    for name in (*schema.KINDS, *schema.TYPE_FIELDS):
        assert f"`{name}`" in text, f"{doc.name} doesn't cover {name}"


def test_the_rules_list_every_element():
    text = RULES.read_text()
    for name in elements():
        assert f"`{name}`" in text or name in ("Answer",), f"CLAUDE.md doesn't list {name}"


def test_the_rules_say_what_to_do_with_every_submission():
    text = RULES.read_text()
    for kind in schema.SUBMISSION_KINDS:
        assert f"`{kind}`" in text, f"CLAUDE.md doesn't cover {kind}"


def test_the_guide_walks_through_the_migration():
    text = GUIDE.read_text()
    for step in ("Send phase A", "page.py reply", "Generate an email", "page.py email", "Accept risk", "Build a deck"):
        assert step in text


def test_the_two_instance_rule_files_match():
    assert RULES.read_text() == (ROOT / "template" / "AGENTS.md").read_text()

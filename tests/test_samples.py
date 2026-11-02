"""The sample pages: valid, loadable, resettable, in the states they claim, and made-up data only."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "template" / "_site"
sys.path.insert(0, str(SITE))

import pagefile  # noqa: E402
import samples  # noqa: E402
import schema  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    samples.load(str(tmp_path), route="app")
    return tmp_path


def doc(folder, name):
    return pagefile.load(folder / f"sample-{name}.json")


def test_every_page_kind_has_a_sample():
    kinds = {samples.read(n)["definition"]["kind"] for n in samples.names()}
    assert {"review", "checklist", "journey", "backlog", "reference"} <= kinds


@pytest.mark.parametrize("name", samples.names())
def test_a_sample_is_valid_once_loaded(folder, name):
    assert schema.validate(doc(folder, name)) == []


def test_a_blocked_item_shows_in_the_summary(folder):
    assert pagefile.summary(doc(folder, "signoff"))["blocked"] == 3


def test_the_round_that_came_back_shows_every_outcome(folder):
    d = doc(folder, "came-back")
    states = pagefile.item_states(d)
    assert states["a"]["hidden"] is True and states["b"]["answer"] == "" and states["c"]["reopened"]
    assert "b" in d["rounds"][-1]["handled"]


def test_a_part_sent_page_holds_only_what_it_sent(folder):
    assert pagefile.held_items(doc(folder, "part-sent")) == {"a"}


def test_loading_again_resets_the_samples_and_leaves_other_pages_alone(folder):
    other = folder / "mine.json"
    pagefile.write_definition(other, {"schema": schema.SCHEMA, "kind": "review", "title": "Mine", "items": [{"id": "a", "title": "A"}]})
    page = folder / "sample-review.json"
    pagefile.save_answers(page, {"s1": {"answer": "yes"}}, by="me")
    samples.load(str(folder), route="app")
    assert doc(folder, "review")["rounds"][-1]["answers"] == {}
    assert other.exists()


def test_the_command_line_loads_them(tmp_path):
    r = subprocess.run([sys.executable, str(SITE / "page.py"), "--root", str(tmp_path), "samples", "demo", "--route", "app"],
                       capture_output=True, text=True, check=True)
    assert "demo/sample-review" in r.stdout
    assert (tmp_path / "demo" / "sample-review.json").exists()


def test_samples_use_only_documentation_addresses():
    text = "".join(json.dumps(samples.read(n)) for n in samples.names())
    for ip in re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text):
        assert ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")), ip

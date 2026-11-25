"""Tests for a page's `"gate": "yes"`: the next item opens only on a confirmed Yes or a Skip."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "template" / "_site"
sys.path.insert(0, str(SITE))

import pagefile  # noqa: E402
import schema  # noqa: E402

from test_serve import request, site  # noqa: E402, F401

T0 = "2026-11-25T07:42:10-04:00"
T1 = "2026-11-25T08:05:44-04:00"


def checks(gate=True):
    d = {"schema": "handoff.page/v1", "kind": "checklist", "title": "Gated", "build": "app 1", "items": [
        {"id": "g1", "title": "One", "skip": True}, {"id": "g2", "title": "Two", "skip": True},
        {"id": "g3", "title": "Three", "skip": True}, {"id": "i1", "type": "info", "title": "Note"}]}
    if gate:
        d["gate"] = "yes"
    return d


@pytest.fixture
def path(tmp_path):
    p = tmp_path / "app" / "gated.json"
    p.parent.mkdir(parents=True)
    return p


def make(path, definition=None):
    pagefile.write_definition(path, definition or checks(), now=T0)
    return path


def put(path, **answers):
    return pagefile.save_answers(path, answers, by="me", now=T1)


def blocked(path):
    return pagefile.blocked_items(pagefile.load(path))


YES = {"answer": "yes", "confirmed": True}


def test_without_a_gate_nothing_waits_and_a_plain_yes_is_fine(path):
    make(path, checks(gate=False))
    assert blocked(path) == set()
    put(path, g2={"answer": "yes"})
    assert pagefile.load(path)["rounds"][-1]["answers"]["g2"].get("confirmed") is None


def test_a_gated_page_blocks_every_item_after_the_first(path):
    make(path)
    assert blocked(path) == {"g2", "g3"}
    assert pagefile.summary(pagefile.load(path))["blocked"] == 2


@pytest.mark.parametrize("answer", [{"answer": "changes", "note": "fix"}, {"answer": "no"}, {}])
def test_only_yes_or_skip_unlocks_the_next_item(path, answer):
    make(path)
    if answer:
        put(path, g1=answer)
    assert "g2" in blocked(path)
    with pytest.raises(pagefile.PageError, match="Waiting for g1 to be Yes"):
        put(path, g2=YES)


def test_a_confirmed_yes_unlocks_the_next_item(path):
    make(path)
    put(path, g1=YES)
    assert blocked(path) == {"g3"}
    put(path, g2=YES)
    assert blocked(path) == set()


def test_a_skip_unlocks_the_next_item(path):
    make(path)
    put(path, g1={"answer": "skipped", "note": "not needed"})
    assert blocked(path) == {"g3"}
    put(path, g2={"answer": "changes", "note": "x"})
    assert "g3" in blocked(path)


def test_a_yes_has_to_be_confirmed(path):
    make(path)
    with pytest.raises(pagefile.PageError, match="has to be confirmed"):
        put(path, g1={"answer": "yes"})
    with pytest.raises(pagefile.PageError, match="has to be confirmed"):
        put(path, g1={"answer": "yes", "confirmed": False})
    assert "g2" in blocked(path)
    assert pagefile.item_states(pagefile.load(path))["g1"]["confirmed"] is False


def test_a_confirmed_yes_is_recorded_and_locked(path):
    make(path)
    put(path, g1=YES)
    assert pagefile.load(path)["rounds"][-1]["answers"]["g1"]["confirmed"] is True
    put(path, g1=YES)
    with pytest.raises(pagefile.PageError, match="confirmed and locked"):
        put(path, g1={"answer": "changes", "note": "oops"})


def test_a_yes_and_the_next_answer_can_arrive_together(path):
    make(path)
    put(path, g2=YES, g1=YES)
    assert blocked(path) == set()


def test_reopening_reblocks_open_items_but_keeps_answered_ones(path):
    make(path)
    put(path, g1=YES, g2=YES)
    pagefile.reply(path, "g1", "ops", "Look again", action="reopen", reason="Numbers moved", now=T1)
    doc = pagefile.load(path)
    assert blocked(path) == {"g3"}, "the open g3 waits again; g2 keeps its Yes"
    assert doc["rounds"][-1]["answers"]["g2"]["answer"] == "yes"
    with pytest.raises(pagefile.PageError, match="Waiting for g1 to be Yes"):
        put(path, g3=YES)
    put(path, g1=YES)
    assert blocked(path) == set()


def test_accept_risk_on_a_round_does_not_unlock_either(path):
    d = {"schema": "handoff.page/v1", "kind": "round", "title": "Plan", "gate": "yes",
         "items": [{"id": "a1", "title": "a"}, {"id": "a2", "title": "b"}]}
    make(path, d)
    put(path, a1={"answer": "risk", "note": "shown in the release notes"})
    assert blocked(path) == {"a2"}


def test_a_yes_unlocked_by_an_edit_of_the_step_text_reblocks_the_next_open_item(path):
    make(path)
    put(path, g1=YES)
    edited = checks()
    edited["items"][0]["title"] = "One, reworded"
    pagefile.write_definition(path, edited, now=T1)
    assert "g2" in blocked(path)
    with pytest.raises(pagefile.PageError, match="Waiting for g1 to be Yes"):
        put(path, g2=YES)


def test_info_items_sit_outside_the_chain(path):
    make(path)
    assert "i1" not in blocked(path)


def test_gate_must_be_yes(path):
    bad = checks()
    bad["gate"] = "no"
    assert any(e.startswith("gate:") for e in schema.validate(bad))
    assert schema.validate(checks()) == []


def test_page_new_takes_a_gate_flag(tmp_path):
    root = tmp_path / "site"
    (root / "app").mkdir(parents=True)
    (root / "site.json").write_text(json.dumps({"owner": "Alex", "key_prefix": "review:", "folders": [{"id": "app", "name": "App"}]}))
    r = subprocess.run([sys.executable, str(SITE / "page.py"), "--root", str(root), "new", "app/gated", "--gate", "yes"],
                       input=json.dumps(checks(gate=False)), capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert pagefile.load(root / "app" / "gated.json")["gate"] == "yes"


def api(base, path, obj, method):
    status, body, _ = request(base + path, method, json.dumps(obj))
    return status, body


def test_the_answer_api_refuses_a_blocked_item(site):  # noqa: F811
    root, base = site
    pagefile.write_definition(root / "demo" / "gated.json", checks(), now=T0)
    url = "/_page/demo/gated/answers"
    status, body = api(base, url, {"answers": {"g2": YES}}, "PUT")
    assert status >= 400 and b"Waiting for g1 to be Yes" in body
    status, body = api(base, url, {"answers": {"g1": {"answer": "yes"}}}, "PUT")
    assert status >= 400 and b"has to be confirmed" in body
    assert api(base, url, {"answers": {"g1": YES}}, "PUT")[0] == 200
    assert api(base, url, {"answers": {"g2": YES}}, "PUT")[0] == 200


def test_a_blocked_item_cannot_be_sent(site):  # noqa: F811
    root, base = site
    pagefile.write_definition(root / "demo" / "gated.json", checks(), now=T0)
    status, body = api(base, "/_page/demo/gated/send", {"kind": "send", "scope": "item", "items": ["g2"], "results": "R"}, "POST")
    assert status >= 400 and b"blocked" in body

"""Tests for template/_site/schema.py: the handoff.page/v1 validator. Every error names its JSON path."""

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template" / "_site"))

import schema  # noqa: E402

KINDS = ["review", "checklist", "journey", "backlog", "questions", "reference", "status"]


def page(kind="review", items=None, **extra):
    doc = {
        "schema": "handoff.page/v1",
        "rev": 1,
        "kind": kind,
        "title": "A page",
        "items": items if items is not None else [],
        "rounds": [{"round": 1, "build": None, "reset": None, "opened": "2026-10-26T08:00:00-04:00", "closed": None,
                    "openedBy": "created", "answers": {}, "checkpoints": {}, "reopened": {}}],
        "thread": {},
        "submissions": [],
    }
    if kind == "checklist":
        doc["build"] = "app 8feb547"
    if kind == "backlog":
        doc["options"] = {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"}
    doc.update(extra)
    return doc


def errors(doc):
    return schema.validate(doc)


DEFAULT_ITEM = {
    "review": {"id": "s1", "title": "Purpose", "body": [{"p": "Why."}]},
    "checklist": {"id": "c1", "title": "Install", "howto": [{"olist": ["Run it"]}]},
    "journey": {"id": "j1", "title": "Sign in", "steps": ["Open the page", "Sign in"], "checkpoint": "signed-in"},
    "backlog": {"id": "b1", "title": "Backlog 1: dark mode", "body": [{"p": "Add it."}]},
    "questions": {"id": "q1", "title": "Which port?", "suggested": "5390"},
    "reference": {"id": "r1", "title": "Notes", "body": [{"copy": "Hello"}]},
    "status": {"id": "st1", "title": "Now", "body": [{"p": "Building."}]},
}


@pytest.mark.parametrize("kind", KINDS)
def test_a_minimal_page_of_every_kind_is_valid(kind):
    assert errors(page(kind, [DEFAULT_ITEM[kind]])) == []


VALID_ITEMS = [
    ("section", {"id": "a", "type": "section", "title": "T", "body": [{"p": "x"}], "section": "Design"}),
    ("check", {"id": "a", "type": "check", "title": "T", "body": [{"p": "x"}], "howto": [{"code": "make", "lang": "sh"}],
               "dependsOn": ["b"], "blockedBy": "example-org/app#70"}),
    ("step", {"id": "a", "type": "step", "title": "T", "steps": ["one", "two"], "checkpoint": "after-install", "dependsOn": []}),
    ("screen", {"id": "a", "type": "screen", "title": "T", "images": [{"src": "img/a.png", "alt": "A", "caption": "c"}],
                "fields": [{"name": "email", "type": "text", "rule": "required"}]}),
    ("contract", {"id": "a", "type": "contract", "title": "T", "fields": [{"name": "id", "type": "int", "rule": ""}],
                  "forms": [{"name": "New", "fields": [{"name": "x", "type": "text", "rule": ""}]}]}),
    ("diff", {"id": "a", "type": "diff", "title": "T", "old": "one", "new": "two", "code": False}),
    ("question", {"id": "a", "type": "question", "title": "T", "body": [{"p": "?"}], "suggested": "yes"}),
    ("info", {"id": "a", "type": "info", "title": "T", "body": [{"note": "careful", "tone": "warn"}]}),
]
OTHER = {"id": "b", "title": "Other"}


@pytest.mark.parametrize(("type_", "item"), VALID_ITEMS, ids=[t for t, _ in VALID_ITEMS])
def test_every_item_type_has_a_valid_form(type_, item):
    assert errors(page("review", [item, OTHER])) == []


def test_a_choice_item_is_valid_on_a_backlog():
    assert errors(page("backlog", [{"id": "b1", "type": "choice", "title": "T", "body": [{"p": "x"}]}])) == []


INVALID_ITEMS = [
    ("section", {"body": "text"}, "items[a].body: expected a list of blocks"),
    ("check", {"howto": [{"p": 3}]}, "items[a].howto[#1].p: expected a string"),
    ("step", {"steps": ["ok", 2]}, "items[a].steps: expected a list of strings"),
    ("screen", {"images": [{"src": "data:image/png;base64,AAAA", "alt": "A"}]},
     "items[a].images[#1].src: pictures are files next to the page, such as img/a.png"),
    ("contract", {"forms": [{"fields": []}]}, "items[a].forms[#1].name: required"),
    ("diff", {"old": "one"}, "items[a].new: required"),
    ("question", {"suggested": 5}, "items[a].suggested: expected a string"),
    ("info", {"dependsOn": ["b"]}, "items[a].dependsOn: not allowed on a info item"),
]


@pytest.mark.parametrize(("type_", "change", "message"), INVALID_ITEMS, ids=[t for t, _, _ in INVALID_ITEMS])
def test_every_item_type_has_an_invalid_form_with_its_path(type_, change, message):
    base = dict(next(item for t, item in VALID_ITEMS if t == type_))
    if type_ == "diff":
        base.pop("new")
    item = {**base, **change}
    assert message in errors(page("review", [item, OTHER]))


def test_an_invalid_choice_names_its_path():
    doc = page("backlog", [{"id": "b1", "type": "choice", "title": "T", "steps": ["x"]}])
    assert "items[b1].steps: not allowed on a choice item" in errors(doc)


VALID_BLOCKS = [
    {"p": "**bold** and `code`"},
    {"list": ["a", "b"]},
    {"olist": ["a", "b"]},
    {"code": "go test ./...", "lang": "sh"},
    {"image": "img/a.png", "alt": "A", "caption": "c"},
    {"table": [["h1", "h2"], ["a", "b"]]},
    {"diff": {"old": "a", "new": "b", "code": True}},
    {"copy": "Dear team"},
    {"note": "Careful", "tone": "warn"},
    {"html": "<b>x</b>"},
]


@pytest.mark.parametrize("block", VALID_BLOCKS, ids=[next(iter(b)) for b in VALID_BLOCKS])
def test_every_block_has_a_valid_form(block):
    assert errors(page("review", [{"id": "a", "title": "T", "body": [block]}])) == []


INVALID_BLOCKS = [
    ({"p": ["x"]}, "items[a].body[#1].p: expected a string"),
    ({"list": "a"}, "items[a].body[#1].list: expected a list of strings"),
    ({"olist": [1]}, "items[a].body[#1].olist: expected a list of strings"),
    ({"code": "x", "lang": 3}, "items[a].body[#1].lang: expected a string"),
    ({"image": "../secret.png"}, "items[a].body[#1].image: pictures are files next to the page, such as img/a.png"),
    ({"table": [["h1", "h2"], ["a"]]}, "items[a].body[#1].table[#2]: expected 2 cells like the header"),
    ({"diff": {"old": "a"}}, "items[a].body[#1].diff.new: required"),
    ({"copy": None}, "items[a].body[#1].copy: expected a string"),
    ({"note": "x", "tone": "loud"}, "items[a].body[#1].tone: expected one of info, warn, ok, danger"),
    ({"html": 1}, "items[a].body[#1].html: expected a string"),
]


@pytest.mark.parametrize(("block", "message"), INVALID_BLOCKS, ids=[next(iter(b)) for b, _ in INVALID_BLOCKS])
def test_every_block_has_an_invalid_form_with_its_path(block, message):
    assert message in errors(page("review", [{"id": "a", "title": "T", "body": [block]}]))


def test_an_unknown_block_is_refused():
    assert "items[a].body[#1]: expected one block key: p, list, olist, code, image, table, diff, copy, note, html" in errors(
        page("review", [{"id": "a", "title": "T", "body": [{"para": "x"}]}]))


INVALID_KINDS = [
    ("review", {"items": [{"id": "a", "title": "T", "answers": ["yes", "maybe"]}]},
     "items[a].answers: expected values from yes, no, changes, skipped"),
    ("checklist", {"build": None}, "build: required on a checklist"),
    ("journey", {"items": [{"id": "j", "title": "T", "steps": "one"}]}, "items[j].steps: expected a list of strings"),
    ("backlog", {"options": None}, "options: required on a backlog"),
    ("questions", {"items": [{"id": "q", "title": "T", "suggested": 1}]}, "items[q].suggested: expected a string"),
    ("reference", {"items": [{"id": "r", "type": "section", "title": "T"}]}, "items[r].type: a reference page holds info items only"),
    ("status", {"items": [{"id": "s", "type": "check", "title": "T"}]}, "items[s].type: a status page holds info items only"),
]


@pytest.mark.parametrize(("kind", "change", "message"), INVALID_KINDS, ids=[k for k, _, _ in INVALID_KINDS])
def test_every_kind_has_an_invalid_form_with_its_path(kind, change, message):
    doc = page(kind, [DEFAULT_ITEM[kind]])
    doc.update(change)
    assert message in errors(doc)


def test_top_level_shape():
    doc = page()
    doc["schema"] = "handoff.page/v2"
    doc["kind"] = "poster"
    doc["colour"] = "red"
    del doc["title"]
    found = errors(doc)
    assert "schema: expected handoff.page/v1" in found
    assert "kind: expected one of review, checklist, journey, backlog, questions, reference, status" in found
    assert "colour: unknown key" in found
    assert "title: required" in found


def test_status_route_and_options_shapes():
    doc = page("backlog", status={"state": "later", "note": 1, "chips": "New", "priority": "high"},
               route={"to": "Bad Name", "mode": "post"})
    doc["options"] = {"choices": [{"value": "start"}], "default": "go"}
    found = errors(doc)
    assert "status.state: expected one of needs-you, reference, done" in found
    assert "status.note: expected a string" in found
    assert "status.chips: expected a list of strings" in found
    assert "status.priority: expected an integer" in found
    assert "route.to: expected an agent name like ops or app" in found
    assert "route.mode: expected one of send, copy, both" in found
    assert "options.choices[#1].label: required" in found
    assert "options.default: expected one of the choice values" in found


def test_item_ids_are_checked():
    doc = page("review", [{"id": "Bad Id", "title": "T"}, {"id": "a", "title": "T"}, {"id": "a", "title": "U"},
                          {"id": "c", "title": "T", "dependsOn": ["c", "zz"]}, {"title": "no id"}])
    found = errors(doc)
    assert "items[#1].id: expected a-z, 0-9, _ and -, starting with a letter or digit, up to 41 characters" in found
    assert "items[a].id: duplicate id" in found
    assert "items[c].dependsOn: c depends on itself" in found
    assert "items[c].dependsOn: no item zz on this page" in found
    assert "items[#5].id: required" in found


def test_rounds_are_numbered_from_1_and_only_the_last_is_open():
    doc = page()
    r1 = doc["rounds"][0]
    doc["rounds"] = [dict(r1, round=0), dict(r1, round=2)]
    found = errors(doc)
    assert "rounds[#1].round: expected 1" in found
    assert "rounds[#1].closed: only the last round is open" in found


def test_round_answers_and_history_shape():
    doc = page("review", [{"id": "a", "title": "T"}])
    doc["rounds"][0]["answers"] = {"a": {"answer": "yes", "note": "", "by": "Alex", "at": "t", "hash": "h",
                                         "was": [{"answer": "no", "note": "", "at": "t0"}, {"answer": 2}]}}
    assert "rounds[#1].answers.a.was[#2].answer: expected a string" in errors(doc)


def test_thread_replies_are_numbered_from_1():
    doc = page("review", [{"id": "a", "title": "T"}])
    doc["thread"] = {"a": [{"n": 0, "from": "ops", "at": "t", "round": 1, "text": "hi"}],
                     "_page": [{"n": 1, "from": "app", "at": "t", "round": 1, "text": "ok", "action": "shout"}]}
    found = errors(doc)
    assert "thread.a[#1].n: expected 1" in found
    assert "thread._page[#1].action: expected one of filed, fixed, reopen, unblock, wontfix, info" in found


def test_validate_does_not_change_the_document():
    doc = page("journey", [DEFAULT_ITEM["journey"]])
    before = copy.deepcopy(doc)
    schema.validate(doc)
    assert doc == before


def test_submissions_shape():
    doc = page()
    doc["submissions"] = [{"n": 1, "kind": "send", "at": "t", "to": "ops", "round": 1, "rev": 3, "items": ["a"], "file": "5-x.json",
                           "state": "lost", "extra": 1}]
    found = errors(doc)
    assert "submissions[#1].state: expected one of sent, taken, failed" in found
    assert "submissions[#1].extra: unknown key" in found

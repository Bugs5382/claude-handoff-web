"""End-to-end tests for the page file endpoints in template/_site/serve.py: /_page/, /_index/, the inbox and Stale."""

import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template" / "_site"))

import pagefile  # noqa: E402
import serve  # noqa: E402

from test_serve import request, site  # noqa: E402, F401

DESIGN = {"schema": "handoff.page/v1", "kind": "review", "title": "Settings design", "items": [
    {"id": "s1", "title": "Purpose"}, {"id": "s2", "title": "Layout"}, {"id": "q1", "type": "question", "title": "Port?"}]}
JOURNEY = {"schema": "handoff.page/v1", "kind": "journey", "title": "Journey 1", "build": "app 1", "items": [
    {"id": "j1", "title": "Install", "steps": ["Run it"], "checkpoint": "after-install"},
    {"id": "j2", "title": "Order", "steps": ["Order"]}]}


def put_json(base, path, obj, method="PUT"):
    status, body, headers = request(base + path, method, json.dumps(obj))
    return status, (json.loads(body) if body and headers.get("Content-Type") == "application/json" else body), headers


def post(base, path, obj):
    return put_json(base, path, obj, "POST")


@pytest.fixture()
def pages(site):  # noqa: F811
    root, base = site
    pagefile.write_definition(root / "demo" / "design.json", DESIGN)
    (root / "demo" / "journeys").mkdir()
    pagefile.write_definition(root / "demo" / "journeys" / "first-order.json", JOURNEY)
    return root, base


def inbox(root, agent="ops"):
    d = root / "_inbox" / agent
    return sorted(p.name for p in d.iterdir() if p.is_file() and not p.name.startswith(".")) if d.exists() else []


def test_a_page_url_serves_the_renderer_shell(pages):
    root, base = pages
    status, body, headers = request(base + "/demo/design")
    assert status == 200 and body == (root / "_site" / "app.html").read_bytes()
    assert headers.get("Cache-Control") == "no-store"
    assert request(base + "/demo/journeys/first-order")[0] == 200
    assert request(base + "/demo/missing")[0] == 404


def test_an_old_html_url_redirects_to_the_page(pages):
    _, base = pages
    conn = http.client.HTTPConnection(base.removeprefix("http://"), timeout=10)
    conn.request("GET", "/demo/design.html")
    r = conn.getresponse()
    assert r.status == 301 and r.getheader("Location") == "/demo/design"
    assert request(base + "/demo/design-review.html")[0] == 200


def test_get_page_returns_the_file_with_its_states_and_an_etag(pages):
    _, base = pages
    status, body, headers = request(base + "/_page/demo/design")
    assert status == 200
    got = json.loads(body)
    assert got["page"]["title"] == "Settings design" and got["page"]["rev"] == 1
    assert got["states"]["s1"] == {"answer": "", "hidden": False, "reopened": None, "round": None}
    assert got["summary"]["open"] == 2
    assert got["route"] == {"to": "ops", "mode": "send"} and got["listening"] is False
    etag = headers["ETag"]
    req = urllib.request.Request(base + "/_page/demo/design", headers={"If-None-Match": etag})
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("expected 304")
    except urllib.error.HTTPError as e:
        assert e.code == 304


@pytest.mark.parametrize("path", ["/_page/demo/nope", "/_page/demo/../site.json", "/_page/_site/page", "/_page/demo",
                                  "/_page/Demo/design"])
def test_get_page_refuses_what_is_not_a_page(pages, path):
    _, base = pages
    assert request(base + path)[0] == 404


def test_put_answers_merges_and_stamps_the_owner(pages):
    root, base = pages
    status, body, _ = put_json(base, "/_page/demo/design/answers", {"base": 1, "answers": {"s1": {"answer": "yes", "note": ""}}})
    assert status == 200 and body == {"rev": 2}
    a = pagefile.load(root / "demo" / "design.json")["rounds"][0]["answers"]["s1"]
    assert a["answer"] == "yes" and a["by"] == "Alex"


@pytest.mark.parametrize(
    ("path", "body", "ctype", "code"),
    [
        ("/_page/demo/design/answers", {"answers": {"s1": {"answer": "maybe"}}}, "application/json", 400),
        ("/_page/demo/design/answers", {"answers": ["s1"]}, "application/json", 400),
        ("/_page/demo/nope/answers", {"answers": {}}, "application/json", 404),
        ("/_page/demo/design/answers", {"answers": {}}, "text/plain", 415),
        ("/_page/demo/design/colour", {"answers": {}}, "application/json", 405),
    ],
    ids=["bad-answer", "not-an-object", "no-page", "wrong-type", "unknown-action"],
)
def test_put_answers_rejects(pages, path, body, ctype, code):
    _, base = pages
    status, out, _ = request(base + path, "PUT", json.dumps(body), ctype)
    assert status == code
    if path.endswith("answers") and code == 400 and body["answers"] != ["s1"]:
        assert json.loads(out)["errors"] == ["s1: expected one of yes, no, changes"]


def test_save_round_now(pages):
    root, base = pages
    status, body, _ = post(base, "/_page/demo/design/round", {"results": "Round 1: all good"})
    assert status == 200 and body == {"round": 2}
    assert pagefile.load(root / "demo" / "design.json")["rounds"][0]["results"] == "Round 1: all good"


def test_send_writes_the_inbox_file_atomically(pages):
    root, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes", "note": ""},
                                                              "s2": {"answer": "changes", "note": "Too wide"}}})
    status, body, _ = post(base, "/_page/demo/design/send", {"kind": "send", "results": "R"})
    assert status == 200 and body["n"] == 1 and body["to"] == "ops" and body["listening"] is False
    [name] = inbox(root)
    assert name.startswith("5-") and name.endswith("-demo-design-1.json") and name == body["file"]
    sub = json.loads((root / "_inbox" / "ops" / name).read_text())
    assert sub["schema"] == "handoff.submission/v1" and sub["kind"] == "send" and sub["page"] == "demo/design"
    assert sub["url"].endswith("/demo/design") and sub["round"] == 1 and sub["results"] == "R"
    assert sub["items"] == [{"id": "s1", "n": 1, "answer": "yes", "note": "", "blocker": False},
                            {"id": "s2", "n": 2, "answer": "changes", "note": "Too wide", "blocker": False}]
    assert os.listdir(root / "_inbox" / "ops") == [name]
    assert pagefile.load(root / "demo" / "design.json")["submissions"][0]["file"] == name


def test_a_blocker_sorts_first(pages):
    root, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s2": {"answer": "no", "note": "broken"}}})
    post(base, "/_page/demo/design/send", {"kind": "send", "results": "R"})
    status, body, _ = post(base, "/_page/demo/design/send", {"kind": "blocker", "items": ["s2"], "results": "BLOCKER"})
    assert status == 200
    names = inbox(root)
    assert names[0] == body["file"] and names[0].startswith("0-") and names[1].startswith("5-")
    sub = json.loads((root / "_inbox" / "ops" / names[0]).read_text())
    assert sub["items"] == [{"id": "s2", "n": 2, "answer": "no", "note": "broken", "blocker": True}]


@pytest.mark.parametrize("body", [{"kind": "shout"}, {"kind": "blocker", "items": []}, {"kind": "send", "items": ["zz"]}],
                         ids=["bad-kind", "blocker-needs-one-item", "unknown-item"])
def test_send_rejects(pages, body):
    _, base = pages
    assert post(base, "/_page/demo/design/send", body)[0] == 400


def test_a_copy_route_does_not_send(pages):
    root, base = pages
    pagefile.set_route(root / "demo" / "design.json", "ops", "copy")
    assert post(base, "/_page/demo/design/send", {"kind": "send"})[0] == 409
    assert inbox(root) == []


def test_the_folder_route_comes_from_site_json(pages):
    root, base = pages
    cfg = json.loads((root / "site.json").read_text())
    cfg["routes"] = {"demo": {"to": "app", "mode": "send"}}
    (root / "site.json").write_text(json.dumps(cfg))
    assert post(base, "/_page/demo/design/send", {"kind": "send"})[0] == 200
    assert len(inbox(root, "app")) == 1


def test_listening_tells_a_live_pid_from_a_dead_one(pages):
    root, base = pages
    d = root / "_inbox" / "ops"
    d.mkdir(parents=True)
    (d / ".listening").write_text(str(os.getpid()))
    assert json.loads(request(base + "/_page/demo/design")[1])["listening"] is True
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (d / ".listening").write_text(str(dead.pid))
    assert json.loads(request(base + "/_page/demo/design")[1])["listening"] is False
    (d / ".listening").write_text("not a pid")
    assert json.loads(request(base + "/_page/demo/design")[1])["listening"] is False


def test_a_taken_submission_shows_as_picked_up(pages):
    root, base = pages
    _, body, _ = post(base, "/_page/demo/design/send", {"kind": "send"})
    taken = root / "_inbox" / "ops" / "taken"
    taken.mkdir()
    os.replace(root / "_inbox" / "ops" / body["file"], taken / body["file"])
    sub = json.loads(request(base + "/_page/demo/design")[1])["page"]["submissions"][0]
    assert sub["state"] == "taken" and sub["takenAt"]


def test_restart_opens_a_round_and_sends_a_restart(pages):
    root, base = pages
    put_json(base, "/_page/demo/journeys/first-order/answers", {"answers": {"j1": {"answer": "yes", "note": ""}}})
    status, body, _ = post(base, "/_page/demo/journeys/first-order/restart", {"checkpoint": "after-install"})
    assert status == 200 and body["round"] == 2
    [name] = inbox(root)
    assert name.startswith("0-") and name.endswith("-demo-journeys-first-order-1.json")
    assert json.loads((root / "_inbox" / "ops" / name).read_text())["kind"] == "restart"
    assert post(base, "/_page/demo/journeys/first-order/restart", {"checkpoint": "nowhere"})[0] == 400


def test_the_inbox_is_never_served(pages):
    root, base = pages
    post(base, "/_page/demo/design/send", {"kind": "send"})
    assert request(base + "/_inbox/ops/" + inbox(root)[0])[0] == 404
    assert request(base + "/_inbox/")[0] == 404


def test_stale_moves_a_page_file_to_old_and_marks_it_done(pages):
    root, base = pages
    status, body, _ = post(base, "/_stale", {"folder": "demo", "page": "design"})
    assert status == 200 and body["moved"] == "demo/_old/design.json"
    assert not (root / "demo" / "design.json").exists()
    moved = pagefile.load(root / "demo" / "_old" / "design.json")
    assert moved["status"]["state"] == "done" and moved["status"]["note"].startswith("Stale (Alex, ")
    log = [json.loads(x) for x in (root / "_saved" / "stale-log.json").read_text().splitlines()]
    assert log[-1]["moved"] == "demo/_old/design.json"
    assert post(base, "/_stale", {"folder": "demo", "page": "design"})[0] == 404


def test_stale_refuses_a_protected_page_file(pages):
    root, base = pages
    cfg = json.loads((root / "site.json").read_text())
    cfg["protected"] = ["demo/design"]
    (root / "site.json").write_text(json.dumps(cfg))
    assert post(base, "/_stale", {"folder": "demo", "page": "design"})[0] == 403


def test_folder_index_merges_page_files_with_html_pages(pages):
    root, base = pages
    pagefile.set_status(root / "demo" / "journeys" / "first-order.json", "needs-you", note="Round 1", priority=10)
    status, body, headers = request(base + "/_index/demo")
    assert status == 200
    got = json.loads(body)
    assert got["folder"] == "demo" and got["name"] == "Demo project"
    by = {c["href"]: c for c in got["pages"]}
    assert got["pages"][0]["href"] == "/demo/journeys/first-order"
    assert by["/demo/journeys/first-order"]["note"] == "Round 1" and by["/demo/journeys/first-order"]["open"] == 1
    design = by["/demo/design"]
    assert design["state"] == "needs-you" and design["open"] == 2 and "To review" in design["chips"]
    assert design["kind"] == "review" and design["title"] == "Settings design"
    assert "/demo/design-review.html" in by
    req = urllib.request.Request(base + "/_index/demo", headers={"If-None-Match": headers["ETag"]})
    try:
        urllib.request.urlopen(req, timeout=10)
        raise AssertionError("expected 304")
    except urllib.error.HTTPError as e:
        assert e.code == 304


def test_an_approved_page_file_is_done(pages):
    root, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes", "note": ""}, "s2": {"answer": "yes", "note": ""}}})
    card = next(c for c in json.loads(request(base + "/_index/demo")[1])["pages"] if c["href"] == "/demo/design")
    assert card["state"] == "done" and "Approved" in card["chips"] and "Done" in card["chips"]


def test_a_page_with_changes_stays_up_top_without_to_review(pages):
    _, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes", "note": ""},
                                                              "s2": {"answer": "changes", "note": "Too wide"}}})
    card = next(c for c in json.loads(request(base + "/_index/demo")[1])["pages"] if c["href"] == "/demo/design")
    assert card["state"] == "needs-you" and card["open"] == 0 and "To review" not in card["chips"]


def test_a_backlog_card_shows_its_tally(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "backlog-2.json", {
        "schema": "handoff.page/v1", "kind": "backlog", "title": "Backlog",
        "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
        "items": [{"id": "b1", "title": "One"}, {"id": "b2", "title": "Two"}]})
    card = next(c for c in json.loads(request(base + "/_index/demo")[1])["pages"] if c["href"] == "/demo/backlog-2")
    assert card["tally"] == "0 start · 2 hold" and card["state"] == "needs-you"


def test_root_index_lists_every_folder(pages):
    _, base = pages
    got = json.loads(request(base + "/_index/")[1])
    assert [f["id"] for f in got["folders"]] == ["demo", "guide"]
    assert any(c["href"] == "/demo/design" for c in got["folders"][0]["pages"])
    assert request(base + "/_index/nope")[0] == 404


def test_get_page_renders_diff_items_and_blocks_on_the_server(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "diffs.json", {"schema": "handoff.page/v1", "kind": "review", "title": "Diffs", "items": [
        {"id": "d1", "type": "diff", "title": "Wording", "old": "The core ran at 10 Gb/s.", "new": "The core ran at 20 Gb/s."},
        {"id": "s2", "title": "Body", "body": [{"p": "x"}, {"diff": {"old": "a b", "new": "a c", "code": True}}]}]})
    diffs = json.loads(request(base + "/_page/demo/diffs")[1])["diffs"]
    assert diffs["d1"].startswith('<div class="rvdiff">') and "<del>10</del>" in diffs["d1"] and "<ins>20</ins>" in diffs["d1"]
    assert diffs["s2/body/2"].startswith('<div class="rvdiff code">')


def test_a_send_holds_the_page_only_once_the_inbox_has_the_file(pages):
    root, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "no"}}})
    assert post(base, "/_page/demo/design/send", {"kind": "send", "results": "R"})[0] == 200
    doc = json.loads(request(base + "/_page/demo/design")[1])
    assert doc["page"]["rounds"][-1]["awaiting"] == 1 and len(inbox(root)) == 1
    status, body, _ = put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes"}}})
    assert status == 400 and "sent" in body["errors"][0]
    status, _, _ = post(base, "/_page/demo/design/unlock", {})
    assert status == 200
    assert "awaiting" not in json.loads(request(base + "/_page/demo/design")[1])["page"]["rounds"][-1]
    assert put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes"}}})[0] == 200


def test_a_send_that_cannot_reach_the_inbox_does_not_hold_the_page(pages):
    root, base = pages
    (root / "_inbox").mkdir(exist_ok=True)
    (root / "_inbox" / "ops").write_text("a file where the folder should be")
    status = post(base, "/_page/demo/design/send", {"kind": "send", "results": "R"})[0]
    assert status >= 400
    assert "awaiting" not in json.loads(request(base + "/_page/demo/design")[1])["page"]["rounds"][-1]


def test_a_blocker_does_not_hold_the_page(pages):
    _, base = pages
    assert post(base, "/_page/demo/design/send", {"kind": "blocker", "items": ["s1"], "results": "R"})[0] == 200
    assert "awaiting" not in json.loads(request(base + "/_page/demo/design")[1])["page"]["rounds"][-1]


def test_a_phase_sends_only_its_own_items_and_a_blocked_one_refuses(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "plan.json", {
        "schema": "handoff.page/v1", "kind": "round", "title": "Plan",
        "phases": [{"id": "A", "title": "One"}, {"id": "B", "title": "Two", "dependsOn": ["A"]}],
        "items": [{"id": "A1", "title": "a"}, {"id": "A2", "title": "b"}, {"id": "B1", "title": "c"}]})
    put_json(base, "/_page/demo/plan/answers", {"answers": {"A1": {"answer": "yes"}}})
    assert post(base, "/_page/demo/plan/send", {"kind": "send", "phase": "B", "results": "R"})[0] == 400
    assert post(base, "/_page/demo/plan/send", {"kind": "send", "phase": "A", "results": "R"})[0] == 200
    doc = json.loads(request(base + "/_page/demo/plan")[1])
    assert doc["page"]["submissions"][0]["items"] == ["A1"] and doc["phases"]["B"]["blocked"] == "A"


def test_a_draft_ask_lands_in_the_inbox_and_needs_instructions(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "mail.json", {**DESIGN, "drafts": True})
    assert post(base, "/_page/demo/mail/send", {"kind": "email", "items": ["s1"], "recipient": "Ops", "ask": " "})[0] == 400
    assert post(base, "/_page/demo/mail/send", {"kind": "email", "items": ["s1"], "ask": "Confirm it"})[0] == 400
    ask = {"kind": "email", "items": ["s1"], "recipient": "The network team", "ask": "Confirm it", "tone": "Plain"}
    assert post(base, "/_page/demo/mail/send", ask)[0] == 200
    name = next(n for n in inbox(root) if "mail" in n)
    sub = json.loads((root / "_inbox" / "ops" / name).read_text())
    assert sub["kind"] == "email" and sub["recipient"] == "The network team" and sub["ask"] == "Confirm it" and sub["tone"] == "Plain"
    assert sub["context"]["title"] == "Purpose" and "changed" in sub["context"] and "comments" in sub["context"]
    assert "awaiting" not in pagefile.load(root / "demo" / "mail.json")["rounds"][-1]
    assert post(base, "/_page/demo/design/send", {"kind": "email", "items": ["s1"], "recipient": "x", "ask": "x"})[0] == 400


def test_a_deck_goes_to_the_inbox_with_only_final_items_and_needs_a_framing(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "plan.json", {
        "schema": "handoff.page/v1", "kind": "round", "title": "Plan", "deck": True,
        "items": [{"id": "s1", "title": "a"}, {"id": "s2", "title": "b"}]})
    assert post(base, "/_page/demo/plan/send", {"kind": "deck", "framing": "x"})[0] == 400, "nothing final yet"
    put_json(base, "/_page/demo/plan/answers", {"answers": {"s1": {"answer": "risk", "note": "Said so"}, "s2": {"answer": "no"}}})
    assert post(base, "/_page/demo/plan/send", {"kind": "deck", "framing": " "})[0] == 400
    assert post(base, "/_page/demo/plan/send", {"kind": "deck", "framing": "Timeline and risks"})[0] == 200
    name = next(n for n in inbox(root) if "plan" in n)
    sub = json.loads((root / "_inbox" / "ops" / name).read_text())
    assert sub["kind"] == "deck" and sub["framing"] == "Timeline and risks"
    assert [i["id"] for i in sub["items"]] == ["s1"] and sub["items"][0]["note"] == "Said so"
    assert "awaiting" not in pagefile.load(root / "demo" / "plan.json")["rounds"][-1]


def test_a_handed_over_delivery_keeps_the_agent_listening_for_a_while(pages):
    root, _ = pages
    d = root / "_inbox" / "app"
    d.mkdir(parents=True, exist_ok=True)
    assert serve.is_listening(str(root), "app") is False
    (d / ".handling").write_text("1")
    assert serve.is_listening(str(root), "app") is True and serve.is_waiting(str(root), "app") is False
    old = time.time() - serve.HANDLING_GRACE - 1
    os.utime(d / ".handling", (old, old))
    assert serve.is_listening(str(root), "app") is False


def test_one_item_can_be_sent_on_its_own(pages):
    root, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "changes", "note": "Shorter"}, "s2": {"answer": "yes"}}})
    status, body, _ = post(base, "/_page/demo/design/send", {"kind": "send", "scope": "item", "items": ["s1"], "results": "R"})
    assert status == 200
    doc = pagefile.load(root / "demo" / "design.json")
    assert doc["submissions"][0]["scope"] == "item" and doc["submissions"][0]["items"] == ["s1"]
    assert pagefile.held_items(doc) == {"s1"}, "s2 stays open"
    sub = json.loads((root / "_inbox" / "ops" / inbox(root)[0]).read_text())
    assert sub["scope"] == "item" and [i["id"] for i in sub["items"]] == ["s1"] and sub["items"][0]["note"] == "Shorter"
    again = {"kind": "send", "scope": "item", "items": ["s1"], "results": "R"}
    assert post(base, "/_page/demo/design/send", again)[0] == 400, "already sent"


@pytest.mark.parametrize("body", [
    {"kind": "send", "scope": "item", "items": ["s1", "s2"]},
    {"kind": "send", "scope": "item"},
    {"kind": "send", "scope": "item", "items": ["s2"]},
    {"kind": "send", "scope": "page", "items": ["s1"]},
    {"kind": "blocker", "scope": "item", "items": ["s1"]},
], ids=["two-items", "no-items", "unanswered", "unknown-scope", "not-a-send"])
def test_an_item_send_refuses(pages, body):
    _, base = pages
    put_json(base, "/_page/demo/design/answers", {"answers": {"s1": {"answer": "yes"}}})
    assert post(base, "/_page/demo/design/send", {**body, "results": "R"})[0] == 400


def test_an_item_whose_dependency_is_open_cannot_be_sent(pages):
    root, base = pages
    pagefile.write_definition(root / "demo" / "plan.json", {
        "schema": "handoff.page/v1", "kind": "round", "title": "Plan",
        "items": [{"id": "a1", "title": "a"}, {"id": "a2", "title": "b", "dependsOn": ["a1"]}]})
    put_json(base, "/_page/demo/plan/answers", {"answers": {"a2": {"answer": "yes"}}})
    assert post(base, "/_page/demo/plan/send", {"kind": "send", "scope": "item", "items": ["a2"], "results": "R"})[0] == 400

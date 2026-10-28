"""Smoke tests for JSON pages in a real browser: render.js draws each page file into today's DOM, review.js answers
it, and every feature of the HTML pages still works (design section 11), plus Send, the delivery state, the thread,
Restart and a live redraw. Drives headless Chrome against a real serve.py; skipped when no Chrome or Chromium is
installed. The scenarios live in tests/js/page_smoke.html."""

import html
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from test_review_choices import find_chrome
from test_review_smoke import free_port

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "page_smoke.html"
sys.path.insert(0, str(ROOT / "template" / "_site"))

import pagefile  # noqa: E402

SCENARIOS = [
    "review: answers, notes, card follows answer, green then approved, saved to the page file",
    "review: Changes needs a note; Blocker: send now writes a blocker to the inbox; copy blockers",
    "copy route: Blocker: copy now copies, and there is no Send button",
    "jump bar: Next and the n key walk open items; the picker filters and Enter jumps",
    "saved answers load from the page file; a failed save shows amber",
    "checklist: skip locks, earlier Yes hidden, blocked by a dependency, reopened with its reason, question",
    "question: Use suggestion fills the answer and saves it",
    "backlog: default choice, picking every item turns the bar green, saved",
    "theme toggle works on a rendered page",
    "finished page: green bar and back link; Copy results goes back to the folder",
    "copy results keeps the Copy results format",
    "mark unanswered Yes fills only open items and saves them",
    "diff item: server-drawn word diff with the Diff | Final switch",
    "pictures open in the picture pop-out; How to test opens its pop-out with Copy buttons",
    "history lists closed rounds; Save round now opens the next round",
    "send: partial confirm, an inbox file, and the delivery state",
    "thread: earlier answers and replies show under the item",
    "restart: Restart from a checkpoint opens a new round and carries the steps",
    "live: a change on the server redraws without a reload, after typing stops, keeping the note and scroll",
    "reference page: blocks render and there is no answer bar",
    "mixed page: a section, a two-answer section, a question, a choice, a step and an info item each answer their own way",
    "example pages: every page in example/demo renders, and the answerable ones answer",
]

T0 = "2026-10-26T07:42:10-04:00"
SECTIONS = [{"id": f"r{n}", "title": t, "body": [{"p": f"{t}."}]}
            for n, t in ((1, "A module repo"), (2, "The web app"), (3, "The platform repos"), (4, "Shared config"))]


def review(title, **extra):
    return {"schema": "handoff.page/v1", "kind": "review", "title": title, "items": [dict(i) for i in SECTIONS], **extra}


BACKLOG = {"schema": "handoff.page/v1", "kind": "backlog", "title": "Backlog",
           "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
           "items": [{"id": "b1", "title": "Export as PDF"}, {"id": "b2", "title": "Dark theme"}, {"id": "b3", "title": "Single sign-on"}]}

CHECKLIST = {"schema": "handoff.page/v1", "kind": "checklist", "title": "Checklist", "build": "1.2.3", "items": [
    {"id": "c1", "title": "One"}, {"id": "c2", "title": "Two"}, {"id": "c3", "title": "Three"},
    {"id": "c4", "title": "Four", "dependsOn": ["c2"]}, {"id": "c5", "title": "Five"},
    {"id": "q1", "type": "question", "title": "Which port?", "suggested": "5390"}]}

MEDIA = {"schema": "handoff.page/v1", "kind": "checklist", "title": "Media", "build": "2.0.0", "items": [
    {"id": "m1", "title": "Login screen", "body": [{"image": "img/settings-tabs-top.svg", "alt": "Tabs across the top"}],
     "howto": [{"olist": ["Run it:"]}, {"code": "./install.sh"}]}]}

JOURNEY = {"schema": "handoff.page/v1", "kind": "journey", "title": "Journey", "build": "app 1", "items": [
    {"id": "j1", "title": "Install", "steps": ["Run the installer"], "checkpoint": "after-install"},
    {"id": "j2", "title": "Order", "steps": ["Order a laptop"]}]}

DIFFS = {"schema": "handoff.page/v1", "kind": "review", "title": "Diffs", "items": [
    {"id": "d1", "type": "diff", "title": "Situation", "old": "It never closes. The core ran at 10 Gb/s.",
     "new": "It never closes. The core ran at 20 Gb/s."}]}

REFERENCE = {"schema": "handoff.page/v1", "kind": "reference", "title": "Notes", "items": [
    {"id": "n1", "title": "Email draft", "body": [{"p": "Hello **team**."}, {"copy": "Dear team,"}, {"table": [["A", "B"], ["1", "2"]]}]}]}


MIXED = {"schema": "handoff.page/v1", "kind": "review", "title": "Mixed",
         "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
         "items": [{"id": "s1", "title": "Defaults look right"},
                   {"id": "s2", "title": "Keep the old name", "answers": ["yes", "no"]},
                   {"id": "q1", "type": "question", "title": "Which timezone?", "suggested": "UTC"},
                   {"id": "c1", "type": "choice", "title": "Import the old data"},
                   {"id": "j1", "type": "step", "title": "Run the installer", "steps": ["Run it"]},
                   {"id": "i1", "type": "info", "title": "Background", "body": [{"p": "Read this first."}]}]}


def write_pages(root):
    demo = root / "demo"
    w = pagefile.write_definition
    for name in ("pf-review-1", "pf-review-2", "pf-review-3", "pf-fin", "pf-copyres", "pf-mark", "pf-send", "pf-live"):
        w(demo / f"{name}.json", review(name), now=T0)
    for n in (1, 2):
        w(demo / f"pf-fin-{n}.json", {"schema": "handoff.page/v1", "kind": "review", "title": "Fin", "items": [
            {"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}, now=T0)
    w(demo / "pf-copyroute.json", review("Copy route"), now=T0)
    pagefile.set_route(demo / "pf-copyroute.json", "ops", "copy")
    w(demo / "pf-saved.json", review("Saved"), now=T0)
    pagefile.save_answers(demo / "pf-saved.json", {"r1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    w(demo / "pf-check.json", CHECKLIST, now=T0)
    pagefile.save_answers(demo / "pf-check.json", {"c1": {"answer": "yes", "note": ""}, "c5": {"answer": "yes", "note": ""}},
                          by="Alex", now=T0)
    pagefile.new_round(demo / "pf-check.json", results="Round 1 text", now=T0)
    pagefile.reply(demo / "pf-check.json", "c5", "app", "Fixed in #70.", action="reopen", reason="fixed in #70", now=T0)
    w(demo / "pf-question.json", CHECKLIST, now=T0)
    w(demo / "pf-backlog.json", BACKLOG, now=T0)
    w(demo / "pf-theme.json", review("Theme"), now=T0)
    w(demo / "pf-media.json", MEDIA, now=T0)
    w(demo / "pf-diff.json", DIFFS, now=T0)
    w(demo / "pf-history.json", review("History"), now=T0)
    pagefile.save_answers(demo / "pf-history.json", {"r1": {"answer": "no", "note": "Too vague"}}, by="Alex", now=T0)
    pagefile.new_round(demo / "pf-history.json", results="Round 1: History\n- [r1] NO: A module repo", now=T0)
    w(demo / "pf-thread.json", review("Thread"), now=T0)
    pagefile.save_answers(demo / "pf-thread.json", {"r1": {"answer": "changes", "note": "Name the module"}}, by="Alex", now=T0)
    pagefile.new_round(demo / "pf-thread.json", now=T0)
    pagefile.reply(demo / "pf-thread.json", "r1", "app", "Renamed to core.", action="fixed", now=T0)
    pagefile.reply(demo / "pf-thread.json", "_page", "app", "Round 2 is ready.", now=T0)
    w(demo / "pf-journey.json", JOURNEY, now=T0)
    pagefile.save_answers(demo / "pf-journey.json", {"j1": {"answer": "yes", "note": ""}, "j2": {"answer": "no", "note": "Broken"}},
                          by="Alex", now=T0)
    w(demo / "pf-reference.json", REFERENCE, now=T0)
    w(demo / "pf-mixed.json", MIXED, now=T0)


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("Chrome or Chromium is not installed")
    tmp = tmp_path_factory.mktemp("pagesmoke")
    root = tmp / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(ROOT / "example" / d, root / d)
    shutil.copy(ROOT / "example" / "site.json", root / "site.json")
    shutil.copy(HARNESS, root / "harness.html")
    write_pages(root)
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(root / "_site" / "serve.py"), str(port), "--bind", "127.0.0.1",
                             "--directory", str(root)], stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.05)
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                            f"--user-data-dir={tmp / 'profile'}", "--virtual-time-budget=180000", "--dump-dom",
                            f"{base}/harness.html"], capture_output=True, text=True, timeout=300)
        m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
        assert m, r.stdout[-2000:] + r.stderr[-2000:]
        data = json.loads(html.unescape(m.group(1)))
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert "harness" not in data, data["harness"]
    data["_root"] = str(root)
    return data


@pytest.mark.parametrize("name", SCENARIOS)
def test_page_smoke(smoke, name):
    assert smoke.get(name) == "ok", smoke.get(name, "did not run")


def test_the_blocker_and_the_send_reached_the_inbox(smoke):
    inbox = Path(smoke["_root"]) / "_inbox" / "ops"
    subs = [json.loads(p.read_text()) for p in sorted(inbox.glob("*.json"))]
    kinds = {(s["page"], s["kind"]) for s in subs}
    assert ("demo/pf-review-2", "blocker") in kinds and ("demo/pf-send", "send") in kinds
    blocker = next(s for s in subs if s["kind"] == "blocker")
    assert blocker["items"][0]["id"] == "r1" and blocker["items"][0]["blocker"] is True
    assert blocker["results"].startswith("BLOCKER: ")

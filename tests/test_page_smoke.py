"""Smoke tests for JSON pages in a real browser: render.js draws each page file into today's DOM, review.js answers
it, and every feature of the HTML pages still works (design section 11), plus Send, the delivery state, the thread,
Restart and a live redraw. Drives headless Chrome against a real serve.py; skipped when no Chrome or Chromium is
installed. The scenarios live in tests/js/page_smoke.html."""

import html
import json
import os
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
    "bar: one line from tablet to desktop widths, status text ellipsed; phone tap targets kept",
    "finished page: green bar and back link; Copy results goes back to the folder",
    "copy results keeps the Copy results format",
    "mark unanswered Yes fills only open items and saves them",
    "diff item: server-drawn word diff with the Diff | Final switch",
    "pictures open in the picture pop-out; How to test opens its pop-out with Copy buttons",
    "links: a page link opens a new window, in the page and in the How to test pop-out; # anchors and pictures don't",
    "history lists closed rounds; Save round now opens the next round",
    "send: partial confirm, an inbox file, and the delivery state",
    "thread: earlier answers and replies show under the item",
    "thread: filed, reopen, unblock and won't fix read at a glance; a long thread folds its oldest entries",
    "delivery: sent to a listening agent, picked up, then the agent's reply, in the bar",
    "sent: a banner says it reached the inbox, every item locks, and an update unlocks it live",
    "sent: nobody listening says so on the page, and Unlock opens it again",
    "sent: a Yes it carried is hidden after the update and stays in Copy results",
    "reopened Yes: shows unanswered, and one Yes clears it",
    "restart: Restart from a checkpoint asks first, opens a new round and carries the steps",
    "restart: the restart shows its own delivery state",
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
    w(demo / "pf-thread2.json", review("Thread 2"), now=T0)
    t2 = demo / "pf-thread2.json"
    pagefile.save_answers(t2, {"r1": {"answer": "no", "note": "Broken on a phone"}}, by="Alex", now=T0)
    pagefile.new_round(t2, now="2026-10-26T08:00:00-04:00")
    pagefile.reply(t2, "r1", "ops", "Filed it.", action="filed", ref="example-org/app#70", now="2026-10-26T08:01:00-04:00")
    pagefile.reply(t2, "r1", "app", "Fixed in #70.", action="fixed", now="2026-10-26T08:02:00-04:00")
    pagefile.reply(t2, "r1", "app", "Ready to look at again.", action="reopen", reason="fixed in #70", now="2026-10-26T08:03:00-04:00")
    pagefile.reply(t2, "r1", "app", "The build is up.", action="unblock", now="2026-10-26T08:04:00-04:00")
    pagefile.reply(t2, "r1", "app", "The tablet layout stays as it is.", action="wontfix", now="2026-10-26T08:05:00-04:00")
    for name in ("pf-dlv-sent", "pf-dlv-taken", "pf-dlv-replied", "pf-held", "pf-held-deaf", "pf-held-after", "pf-reopened"):
        w(demo / f"{name}.json", review(name), now=T0)
        pagefile.set_route(demo / f"{name}.json", "app", "send")
    pagefile.set_route(demo / "pf-held-deaf.json", "nobody", "send")
    after = demo / "pf-held-after.json"
    pagefile.save_answers(after, {"r1": {"answer": "yes", "note": ""}, "r2": {"answer": "changes", "note": "Move it"}}, by="Sam", now=T0)
    pagefile.add_submission(after, {"kind": "send", "to": "app", "items": ["r1", "r2"], "file": "y-{n}.json"}, now=T0)
    pagefile.hold(after, 1)
    pagefile.reply(after, "r2", "app", "Moved.", action="fixed", now="2026-10-26T08:00:00-04:00")
    reo = demo / "pf-reopened.json"
    pagefile.save_answers(reo, {"r1": {"answer": "yes", "note": ""}}, by="Sam", now=T0)
    pagefile.reply(reo, "r1", "app", "Look again.", action="reopen", reason="numbers moved", now="2026-10-26T08:00:00-04:00")
    (root / "_inbox" / "app").mkdir(parents=True, exist_ok=True)
    (root / "_inbox" / "app" / ".listening").write_text(str(os.getpid()))
    for name in ("pf-dlv-taken", "pf-dlv-replied"):
        pagefile.add_submission(demo / f"{name}.json", {"kind": "send", "to": "app", "file": "x-{n}.json"}, now=T0)
        pagefile.mark_taken(demo / f"{name}.json", 1, at="2026-10-26T07:43:00-04:00")
    pagefile.reply(demo / "pf-dlv-replied.json", "_page", "app", "All fixed, round 2 is ready.", now="2026-10-26T07:50:00-04:00")
    w(demo / "pf-journey2.json", JOURNEY, now=T0)
    pagefile.save_answers(demo / "pf-journey2.json", {"j1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    w(demo / "pf-bar.json", review("pf-bar"), now=T0)
    pagefile.set_route(demo / "pf-bar.json", "app", "send")
    pagefile.add_submission(demo / "pf-bar.json", {"kind": "send", "to": "app", "file": "x-{n}.json"}, now=T0)
    pagefile.mark_taken(demo / "pf-bar.json", 1, at="2026-10-26T07:43:00-04:00")
    pagefile.reply(demo / "pf-bar.json", "_page", "app", "All fixed, round 2 is ready, and the notes on the module names are in the "
                   "thread below.", now="2026-10-26T07:50:00-04:00")
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

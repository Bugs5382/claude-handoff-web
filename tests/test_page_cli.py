"""Tests for template/_site/page.py, through its command line: the agent's door to page files and its inbox."""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "template" / "_site"
PAGE = SITE / "page.py"
GOLDEN = ROOT / "tests" / "data" / "convert"
sys.path.insert(0, str(SITE))

import pagefile  # noqa: E402

from sites import html_example  # noqa: E402

DESIGN = {"schema": "handoff.page/v1", "kind": "review", "title": "Design", "items": [
    {"id": "s1", "title": "Purpose"}, {"id": "s2", "title": "Layout", "blockedBy": "example-org/app#70"}]}


def run(root, *args, stdin=None):
    return subprocess.run([sys.executable, str(PAGE), "--root", str(root), *args], input=stdin, capture_output=True,
                          text=True, timeout=30)


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "site"
    (r / "app").mkdir(parents=True)
    (r / "site.json").write_text(json.dumps({"owner": "Alex", "key_prefix": "review:", "folders": [{"id": "app", "name": "App"}]}))
    return r


def make(root):
    r = run(root, "new", "app/design", stdin=json.dumps(DESIGN))
    assert r.returncode == 0, r.stderr
    return root / "app" / "design.json"


def test_new_creates_a_page_from_stdin(root):
    path = make(root)
    doc = pagefile.load(path)
    assert doc["rev"] == 1 and doc["title"] == "Design"


def test_new_refuses_an_existing_page_and_a_bad_definition(root):
    make(root)
    r = run(root, "new", "app/design", stdin=json.dumps(DESIGN))
    assert r.returncode == 1 and "app/design already exists; use set" in r.stderr
    bad = dict(DESIGN, items=[{"id": "Bad Id", "title": "T"}])
    r = run(root, "new", "app/other", stdin=json.dumps(bad))
    assert r.returncode == 1 and "items[#1].id:" in r.stderr
    assert not (root / "app" / "other.json").exists()


def test_new_reads_a_file_and_makes_deeper_folders(root, tmp_path):
    src = tmp_path / "def.json"
    src.write_text(json.dumps(DESIGN))
    assert run(root, "new", "app/journeys/first", "--from", str(src)).returncode == 0
    assert (root / "app" / "journeys" / "first.json").exists()


def test_a_page_ref_must_be_folder_and_slug(root):
    r = run(root, "new", "design", stdin=json.dumps(DESIGN))
    assert r.returncode == 1 and "expected <folder>/<slug>" in r.stderr
    r = run(root, "set", "app/nope", stdin=json.dumps(DESIGN))
    assert r.returncode == 1 and "app/nope: no such page" in r.stderr


def test_set_replaces_the_definition_and_a_build_change_opens_a_round(root):
    path = make(root)
    assert run(root, "set", "app/design", stdin=json.dumps(dict(DESIGN, build="app 2"))).returncode == 0
    doc = pagefile.load(path)
    assert doc["build"] == "app 2" and [r["openedBy"] for r in doc["rounds"]] == ["created", "build changed"]


def test_reply_reopen_unblock_and_errors(root):
    path = make(root)
    r = run(root, "reply", "app/design", "s1", "--from", "app", "--reopen", "fixed in #70", "Fixed in #70.")
    assert r.returncode == 0 and r.stdout.strip() == "reply 1 on s1"
    assert run(root, "reply", "app/design", "s2", "--from", "app", "--action", "unblock", "--ref", "example-org/app#70",
               "Landed.").returncode == 0
    assert run(root, "reply", "app/design", "_page", "--from", "app", "Round 2 is ready.").returncode == 0
    doc = pagefile.load(path)
    assert doc["thread"]["s1"][0]["action"] == "reopen" and doc["thread"]["s1"][0]["reason"] == "fixed in #70"
    assert doc["rounds"][-1]["reopened"] == {"s1": "fixed in #70"}
    assert doc["thread"]["s2"][0]["ref"] == "example-org/app#70" and doc["thread"]["_page"][0]["n"] == 1
    r = run(root, "reply", "app/design", "zz", "--from", "app", "?")
    assert r.returncode == 1 and "zz: no item zz on this page" in r.stderr


def test_status_route_and_round_close(root):
    path = make(root)
    assert run(root, "status", "app/design", "done", "--note", "Shipped in 1.4", "--chip", "Shipped", "--priority", "10").returncode == 0
    assert run(root, "route", "app/design", "--to", "app", "--mode", "both").returncode == 0
    r = run(root, "round-close", "app/design", "--results", "Round 1 text")
    assert r.returncode == 0 and r.stdout.strip() == "round 2 open"
    doc = pagefile.load(path)
    assert doc["status"] == {"state": "done", "note": "Shipped in 1.4", "chips": ["Shipped"], "priority": 10}
    assert doc["route"] == {"to": "app", "mode": "both"}
    assert doc["rounds"][0]["results"] == "Round 1 text"
    assert run(root, "route", "app/design", "--to", "app", "--mode", "shout").returncode == 2


def test_check_prints_errors_with_paths(root, tmp_path):
    make(root)
    assert run(root, "check", "app/design").returncode == 0
    bad = tmp_path / "bad.json"
    doc = pagefile.load(root / "app" / "design.json")
    doc["items"][0]["body"] = [{"note": "x", "tone": "loud"}]
    bad.write_text(json.dumps(doc))
    r = run(root, "check", str(bad))
    assert r.returncode == 1 and "items[s1].body[#1].tone: expected one of info, warn, ok, danger" in r.stdout


def inbox(root, agent="ops"):
    d = root / "_inbox" / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_wait_exits_at_once_when_files_are_waiting_blockers_first(root):
    d = inbox(root)
    (d / "5-20261026T100000Z-app-design-1.json").write_text("{}")
    (d / "0-20261026T100001Z-app-design-2.json").write_text("{}")
    (d / "taken").mkdir()
    (d / "taken" / "5-old.json").write_text("{}")
    r = run(root, "wait", "ops")
    assert r.returncode == 0
    assert [Path(x).name for x in r.stdout.split()] == ["0-20261026T100001Z-app-design-2.json", "5-20261026T100000Z-app-design-1.json"]
    assert not (d / ".listening").exists()


@pytest.mark.parametrize("mode", [[], ["--poll", "--interval", "0.1"]], ids=["kqueue", "fallback"])
def test_wait_exits_when_a_file_arrives_and_catches_a_burst(root, mode):
    d = inbox(root)
    proc = subprocess.Popen([sys.executable, str(PAGE), "--root", str(root), "wait", "ops", *mode], stdout=subprocess.PIPE, text=True)
    for _ in range(100):
        if (d / ".listening").exists():
            break
        time.sleep(0.02)
    assert (d / ".listening").read_text().strip() == str(proc.pid)
    time.sleep(0.2)
    assert proc.poll() is None
    (d / "5-a.json").write_text("{}")
    (d / "0-b.json").write_text("{}")
    out, _ = proc.communicate(timeout=10)
    assert proc.returncode == 0
    assert [Path(x).name for x in out.split()] == ["0-b.json", "5-a.json"]
    assert not (d / ".listening").exists()


def test_wait_times_out_quietly(root):
    inbox(root)
    r = run(root, "wait", "ops", "--timeout", "0.3")
    assert r.returncode == 3 and r.stdout == ""


def test_hook_is_quiet_only_when_listening_and_empty(root):
    d = inbox(root)
    (d / ".listening").write_text(str(os.getpid()))
    r = run(root, "hook", "ops")
    assert r.returncode == 0 and r.stdout == ""
    (d / "5-a.json").write_text("{}")
    assert "1 submission waiting for ops" in run(root, "hook", "ops").stdout
    (d / "5-a.json").unlink()
    (d / ".listening").unlink()
    out = run(root, "hook", "ops").stdout
    assert "nothing is listening for ops" in out and "page.py" in out and out.count("\n") == 1


@pytest.fixture
def demo(tmp_path):
    r = tmp_path / "site"
    shutil.copytree(ROOT / "template", r)
    shutil.copytree(html_example("demo"), r / "demo")
    shutil.copy(ROOT / "example" / "site.json", r / "site.json")
    return r


@pytest.mark.parametrize("page", ["design-review", "backlog", "signoff-checklist"])
def test_convert_matches_the_golden_file_for_every_example_page(demo, page):
    r = run(demo, "convert", str(demo / "demo" / f"{page}.html"), "--print")
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout)
    assert got == json.loads((GOLDEN / f"{page}.json").read_text())
    assert pagefile.validate(dict(got, rev=1, rounds=[{"round": 1, "build": None, "reset": None, "opened": "t", "closed": None,
                                                      "openedBy": "x", "answers": {}}], thread={}, submissions=[])) == []


def test_convert_writes_the_page_with_saved_answers_and_history(demo):
    saved = demo / "_saved"
    (saved / "history" / "review-demo-design-review.html").mkdir(parents=True)
    (saved / "review-demo-design-review.html.json").write_text(json.dumps({
        "s1": {"v": "yes", "n": ""}, "s2": {"v": "chg", "n": "Tabs down the side"}, "s4": {"a": "14 days"}, "_meta": {"x": 1}}))
    (saved / "history" / "review-demo-design-review.html" / "20261020T100000Z__1.json").write_text(json.dumps({
        "page": "demo/design-review.html", "round": 1, "build": "", "opened": "2026-10-19T09:00:00+00:00",
        "closed": "2026-10-20T10:00:00+00:00", "answers": {"s1": {"v": "no", "n": "Too vague"}}, "results_text": "Round 1: ..."}))
    r = run(demo, "convert", str(demo / "demo" / "design-review.html"))
    assert r.returncode == 0, r.stderr
    doc = pagefile.load(demo / "demo" / "design-review.json")
    assert [x["round"] for x in doc["rounds"]] == [1, 2]
    old, cur = doc["rounds"]
    assert old["closed"] == "2026-10-20T10:00:00+00:00" and old["results"] == "Round 1: ..."
    assert old["answers"]["s1"]["answer"] == "no" and old["answers"]["s1"]["note"] == "Too vague"
    assert cur["closed"] is None
    assert {k: (v["answer"], v["note"]) for k, v in cur["answers"].items()} == {
        "s1": ("yes", ""), "s2": ("changes", "Tabs down the side"), "s4": ("14 days", "")}
    assert cur["answers"]["s1"]["by"] == "Alex"
    assert (demo / "demo" / "design-review.html").exists()
    r = run(demo, "convert", str(demo / "demo" / "design-review.html"))
    assert r.returncode == 1 and "demo/design-review already exists" in r.stderr


def test_convert_keeps_what_it_cannot_map_as_a_flagged_html_block(demo):
    page = demo / "demo" / "odd.html"
    page.write_text('<!doctype html><html><head><title>Odd</title></head><body class="site"><main>'
                    "<h2>One</h2><details><summary>More</summary><p>x</p></details></main></body></html>")
    r = run(demo, "convert", str(page), "--print")
    assert r.returncode == 0
    assert json.loads(r.stdout)["items"][0]["body"] == [{"html": "<details><summary>More</summary><p>x</p></details>"}]
    assert "odd: s1: kept a <details> as an html block" in r.stderr

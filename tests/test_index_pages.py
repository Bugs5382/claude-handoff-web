"""Indexes and history built from page files: gen-index.py merges them with the HTML pages, and serve.py builds the
folder, root and history pages on request when a folder has page files."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "template" / "_site"))

import pagefile  # noqa: E402

from test_serve import request, site  # noqa: E402, F401

T0 = "2026-10-26T07:42:10-04:00"


def review(title, n=2, **extra):
    return {"schema": "handoff.page/v1", "kind": "review", "title": title,
            "items": [{"id": f"s{i}", "title": f"Item {i}"} for i in range(1, n + 1)], **extra}


@pytest.fixture()
def tree(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(ROOT / "example" / d, root / d)
    cfg = json.loads((ROOT / "example" / "site.json").read_text())
    cfg["folders"].append({"id": "app", "name": "App", "blurb": "Only page files"})
    (root / "site.json").write_text(json.dumps(cfg))
    (root / "app").mkdir()
    return root


def gen(root):
    r = subprocess.run([sys.executable, str(root / "gen-index.py")], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def cards(html_text):
    return re.findall(r'<li class="card[^"]*" data-key="([^"]+)"', html_text)


def test_gen_index_merges_page_files_with_html_pages_in_order(tree):
    pagefile.write_definition(tree / "demo" / "design.json", review("Settings design"), now=T0)
    pagefile.write_definition(tree / "demo" / "urgent.json", review("Urgent", status={"state": "needs-you", "priority": 10}), now=T0)
    gen(tree)
    folder = (tree / "demo" / "index.html").read_text()
    keys = cards(folder)
    assert keys[0] == "demo/urgent", keys
    assert "demo/design" in keys and "demo/design-review.html" in keys
    card = re.search(r'<li class="card needs" data-key="demo/design".*?</li>', folder, re.S).group(0)
    assert '<a href="/demo/design">Settings design</a>' in card and "2 open" in card and "To review" in card
    assert 'data-stale-page="design"' in card
    root_index = (tree / "index.html").read_text()
    assert 'data-key="demo/design"' in root_index


def test_a_folder_of_page_files_needs_no_status_json(tree):
    pagefile.write_definition(tree / "app" / "plan.json", review("Plan"), now=T0)
    pagefile.save_answers(tree / "app" / "plan.json", {"s1": {"answer": "yes", "note": ""}, "s2": {"answer": "yes", "note": ""}},
                          by="Alex", now=T0)
    gen(tree)
    gen(tree)
    assert not (tree / "app" / "_status.json").exists()
    folder = (tree / "app" / "index.html").read_text()
    keys = cards(folder)
    assert "app/plan" in keys and "app/history/" in keys
    assert "Not classified" not in folder
    plan = re.search(r'<li class="card[^"]*" data-key="app/plan".*?</li>', folder, re.S).group(0)
    assert "Approved" in plan and "Done" in plan
    hist = re.search(r'<li class="card[^"]*" data-key="app/history/".*?</li>', folder, re.S).group(0)
    assert "Reference" in hist


def test_history_page_lists_page_file_rounds(tree):
    path = tree / "app" / "plan.json"
    pagefile.write_definition(path, review("Plan"), now=T0)
    pagefile.save_answers(path, {"s1": {"answer": "yes", "note": ""}}, by="Alex", now=T0)
    pagefile.new_round(path, results="Round 1: Plan\n- [s1] YES: Item 1", now=T0)
    gen(tree)
    hist = (tree / "app" / "history" / "index.html").read_text()
    assert "Plan (1 round)" in hist and "1 of 2 Yes" in hist and "- [s1] YES: Item 1" in hist
    assert '<a href="/app/plan">Full page</a>' in hist


def test_a_backlog_page_file_card_shows_its_tally(tree):
    pagefile.write_definition(tree / "app" / "backlog.json", {
        "schema": "handoff.page/v1", "kind": "backlog", "title": "Backlog",
        "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
        "items": [{"id": "b1", "title": "One"}, {"id": "b2", "title": "Two"}]}, now=T0)
    gen(tree)
    card = re.search(r'data-key="app/backlog".*?</li>', (tree / "app" / "index.html").read_text(), re.S).group(0)
    assert '<span class="tally">0 start · 2 hold</span>' in card


@pytest.fixture()
def live(site):  # noqa: F811
    root, base = site
    pagefile.write_definition(root / "demo" / "design.json", review("Settings design"), now=T0)
    return root, base


def test_the_server_builds_a_folder_index_with_page_files_on_request(live):
    root, base = live
    status, body, headers = request(base + "/demo/")
    assert status == 200 and headers.get("Cache-Control") == "no-store"
    page = body.decode()
    assert 'data-key="demo/design"' in page and 'data-key="demo/design-review.html"' in page and "id=live" in page
    assert "2 open" in re.search(r'data-key="demo/design".*?</li>', page, re.S).group(0)
    pagefile.save_answers(root / "demo" / "design.json", {"s1": {"answer": "yes", "note": ""}}, by="Alex")
    page = request(base + "/demo/")[1].decode()
    assert "1 open" in re.search(r'data-key="demo/design".*?</li>', page, re.S).group(0)


def test_the_server_builds_the_root_and_history_pages_on_request(live):
    root, base = live
    assert 'data-key="demo/design"' in request(base + "/")[1].decode()
    pagefile.save_answers(root / "demo" / "design.json", {"s1": {"answer": "no", "note": ""}}, by="Alex")
    pagefile.new_round(root / "demo" / "design.json", results="Round 1: Settings design")
    hist = request(base + "/demo/history/")[1].decode()
    assert "Settings design (1 round)" in hist and "Round 1: Settings design" in hist


def test_a_folder_without_page_files_is_served_as_a_file(live):
    root, base = live
    (root / "guide" / "index.html").write_text("<!doctype html><title>static guide index</title>")
    assert b"static guide index" in request(base + "/guide/")[1]


def test_the_index_api_lists_each_page_file_once(live):
    _, base = live
    pages = json.loads(request(base + "/_index/demo")[1])["pages"]
    assert [p["href"] for p in pages].count("/demo/design") == 1

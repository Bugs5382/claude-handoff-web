"""Tests for template/gen-index.py's per-folder round-history index."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from sites import html_example

ROOT = Path(__file__).resolve().parent.parent
GEN_INDEX = ROOT / "template" / "gen-index.py"
SERVE = ROOT / "template" / "_site" / "serve.py"


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(html_example(d), root / d)
    shutil.copy(ROOT / "example" / "site.json", root / "site.json")
    return root


def put_history_entry(root, name, round_no, build, answers):
    hdir = root / "_saved" / "history" / name
    hdir.mkdir(parents=True, exist_ok=True)
    entry = {"page": "demo/signoff-checklist.html", "title": "Example app 1.4.0: sign-off checklist",
              "round": round_no, "build": build, "opened": "2026-10-08T07:00:00-04:00",
              "closed": "2026-10-08T10:00:00-04:00", "answers": answers,
              "results_text": f"Round {round_no} results\n"}
    (hdir / f"2026100{round_no}T100000Z__{build}.json").write_text(json.dumps(entry))


def test_page_key_matches_serve_py(site):
    # gen-index.py reads site.json next to itself at import time, so load the copy under `site`.
    gi = load_module(site / "gen-index.py", "gen_index")
    serve = load_module(SERVE, "serve")
    for k in ("review:/demo/signoff-checklist.html", "", "A B/c", "review:/x/y/"):
        assert gi.page_key(k) == serve.page_key(k)


def test_history_index_lists_rounds_and_seeds_reference_state(site):
    name = "review-demo-signoff-checklist.html"
    put_history_entry(site, name, 1, "1.4.0-rc.2", {"t1": {"v": "yes", "n": ""}, "t2": {"v": "no", "n": "broke"}})
    r = subprocess.run([sys.executable, str(site / "gen-index.py")], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    history_html = (site / "demo" / "history" / "index.html").read_text()
    assert "Example app 1.4.0: sign-off checklist (1 round)" in history_html
    assert "Round 1" in history_html and "build 1.4.0-rc.2" in history_html
    assert "1 of 2 Yes" in history_html
    manifest = json.loads((site / "demo" / "_status.json").read_text())
    assert manifest["history/"]["state"] == "reference"
    root_html = (site / "index.html").read_text()
    assert 'href="/demo/history/">History</a>' in root_html


def test_history_index_empty_when_no_rounds(site):
    r = subprocess.run([sys.executable, str(site / "gen-index.py")], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    history_html = (site / "demo" / "history" / "index.html").read_text()
    assert "No rounds yet." in history_html


def test_history_entry_never_forced_needs_you(site):
    """Re-running gen-index.py must never flip an existing history/ entry to needs-you."""
    (site / "demo" / "_status.json").write_text(json.dumps({
        "review/": {"state": "needs-you", "note": "x"},
        "history/": {"state": "reference", "note": "custom note"},
    }))
    r = subprocess.run([sys.executable, str(site / "gen-index.py")], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    manifest = json.loads((site / "demo" / "_status.json").read_text())
    # first_seen is added like for any page gen-index.py lists; the state and note stay as they were.
    assert {k: v for k, v in manifest["history/"].items() if k != "first_seen"} == {"state": "reference", "note": "custom note"}


def card_html(page_html, key):
    m = re.search(r'<li class="card[^"]*" data-key="' + re.escape(key) + r'".*?</li>', page_html, re.S)
    assert m, key
    return m.group(0)


def test_choices_page_card_shows_no_open_items(site):
    """A page with its own answer choices (the example backlog) has nothing open and is never Approved."""
    r = subprocess.run([sys.executable, str(site / "gen-index.py")], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    folder = (site / "demo" / "index.html").read_text()
    backlog = card_html(folder, "demo/backlog.html")
    assert "open item" not in backlog
    assert ">Approved<" not in backlog
    assert ">To review<" in backlog
    # a Yes / No / Changes page next to it still counts its items
    # three Yes / No / Changes items; its open question never counts
    assert '<span class="opn">3 open</span>' in card_html(folder, "demo/design-review.html")


def test_page_mixing_choices_and_yes_no_counts_only_yes_no_items(site):
    gi = load_module(site / "gen-index.py", "gen_index_mix")
    src = ('<body class="site"><h2>Approve the plan</h2><h2 data-review-options="a:A,b:B" data-review-default="a">Pick one</h2>'
           '<section data-review-question="x" data-title="X" data-review-options="a:A,b:B"></section>'
           '<script src="/_site/review.js?v=17"></script></body>')
    assert gi.review_info(src) == (3, 1, 0, 2)


def run_script(site, *args):
    r = subprocess.run([sys.executable, *map(str, args)], cwd=site, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_folder_open_total_counts_unified_page_items_once(site):
    """The unified review page repeats its source pages' items, so the folder total leaves its card out."""
    run_script(site, site / "_site" / "build-review.py", "demo")
    run_script(site, site / "gen-index.py")
    root_html = (site / "index.html").read_text()
    group = re.search(r'<section class="sect grp" data-project="demo".*?</section>', root_html, re.S).group(0)
    per_card = {}
    for card in re.findall(r"<li .*?</li>", group, re.S):
        m = re.search(r'<span class="opn[^"]*">(\d+) open</span>', card)
        per_card[re.search(r'data-key="([^"]+)"', card).group(1)] = int(m.group(1)) if m else 0
    assert "demo/review/" in per_card
    sources = sum(n for k, n in per_card.items() if k != "demo/review/")
    total = int(re.search(r'data-open="(\d+)"', group).group(1))
    assert total == sources
    assert re.search(rf'<div class="ghead">.*?<span>{total} open( · [^<]*)?</span>', group), "the group header shows the same total"


def test_open_questions_and_blocked_items_never_count_as_open(site):
    gi = load_module(site / "gen-index.py", "gen_index_q")
    src = ('<body class="site" data-review-blocked="s2=s1 must pass first"><h2>One</h2><h2>Two</h2>'
           '<h2 data-review-type="question">Anything else?</h2>'
           '<section data-review-question="q2" data-title="Q" data-review-type="question"></section>'
           '<script src="/_site/review.js?v=17"></script></body>')
    n, open_n, _, n_choice = gi.review_info(src)
    assert (n, open_n, n_choice) == (2, 1, 0)


def test_page_of_only_questions_shows_no_count_or_approved(site):
    page = ('<!doctype html><html><head><title>Questions</title></head><body class="site">'
            '<h2 data-review-type="question">Anything else?</h2>'
            '<script src="/_site/review.js?v=17"></script></body></html>')
    (site / "demo" / "questions.html").write_text(page)
    run_script(site, site / "gen-index.py")
    card = card_html((site / "demo" / "index.html").read_text(), "demo/questions.html")
    assert "open item" not in card
    assert ">Approved<" not in card


@pytest.mark.parametrize("entry", [None, {"first_seen": "2026-10-01T09:00:00+00:00"}])
def test_history_card_never_left_under_needs_you(site, entry):
    """history/ already on disk with no manifest state (an older instance, a rewritten manifest) becomes reference."""
    run_script(site, site / "gen-index.py")
    manifest = json.loads((site / "demo" / "_status.json").read_text())
    if entry is None:
        del manifest["history/"]
    else:
        manifest["history/"] = entry
    (site / "demo" / "_status.json").write_text(json.dumps(manifest))
    run_script(site, site / "gen-index.py")
    manifest = json.loads((site / "demo" / "_status.json").read_text())
    assert manifest["history/"]["state"] == "reference"
    if entry:
        assert manifest["history/"]["first_seen"] == entry["first_seen"]
    card = card_html((site / "demo" / "index.html").read_text(), "demo/history/")
    assert 'class="card needs"' not in card and "Not classified" not in card
    root_html = (site / "index.html").read_text()
    now = re.search(r'<section class="sect" data-sect="now">.*?<section class="sect" data-sect="reference">', root_html, re.S).group(0)
    assert 'data-key="demo/history/"' not in now
    ref = re.search(r'<section class="sect" data-sect="reference">.*?</section>', root_html, re.S).group(0)
    assert 'data-key="demo/history/"' in ref, "the root lists it under Reference instead"


def test_history_page_listed_on_the_first_run(site):
    assert not (site / "demo" / "history").exists()
    run_script(site, site / "gen-index.py")
    card = card_html((site / "demo" / "index.html").read_text(), "demo/history/")
    assert ">Demo project: history</a>" in card


def test_history_round_on_a_choices_page_shows_choice_counts(site):
    """A Start/Hold backlog has no Yes; its rounds show the per-choice counts, untouched items on the default."""
    put_history_entry(site, "review-demo-backlog.html", 1, "b1", {"s1": {"v": "start", "n": ""}, "s2": {"v": "", "n": "Not before Q3"}})
    run_script(site, site / "gen-index.py")
    history_html = (site / "demo" / "history" / "index.html").read_text()
    assert "1 start · 2 hold" in history_html
    assert "Yes" not in history_html


def test_asset_folders_are_not_cards(site):
    """A subfolder is a page only when it holds an .html file: img/ is never a card, listed in the manifest or not."""
    manifest = json.loads((site / "demo" / "_status.json").read_text())
    manifest.pop("img/", None)
    (site / "demo" / "_status.json").write_text(json.dumps(manifest))
    (site / "demo" / "files").mkdir()
    (site / "demo" / "files" / "notes.txt").write_text("x")
    (site / "demo" / "report").mkdir()
    (site / "demo" / "report" / "index.html").write_text("<title>Report</title>")
    run_script(site, site / "gen-index.py")
    folder = (site / "demo" / "index.html").read_text()
    assert 'data-key="demo/img/"' not in folder
    assert 'data-key="demo/files/"' not in folder
    assert 'data-key="demo/report/"' in folder
    assert "img/" not in json.loads((site / "demo" / "_status.json").read_text())
    (site / "demo" / "_status.json").write_text(json.dumps({**manifest, "img/": {"state": "reference", "note": "Pictures"}}))
    run_script(site, site / "gen-index.py")
    assert 'data-key="demo/img/"' not in (site / "demo" / "index.html").read_text()

"""Tests for template/gen-index.py's per-folder round-history index."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

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
        shutil.copytree(ROOT / "example" / d, root / d)
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
    assert manifest["history/"] == {"state": "reference", "note": "custom note"}

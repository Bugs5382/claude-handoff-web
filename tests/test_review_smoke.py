"""Smoke tests for the redesigned review controls in a real browser: the segmented answers, the bottom bar's
colour states and Open IDs picker, saved answers, the theme toggle, and the way back to the folder once a
page is finished. Drives headless Chrome against a real serve.py; skipped when no Chrome or Chromium is
installed. The scenarios live in tests/js/review_smoke.html."""

import html
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from test_review_choices import find_chrome

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "tests" / "js" / "review_smoke.html"
REVIEW = '<script src="/_site/review.js"></script>'

SCENARIOS = [
    "backlog: choices start not picked, bar dark, picker says Not picked",
    "backlog: picking every item (Hold included) turns the bar green",
    "backlog: clicking the picked choice again returns it to the default",
    "review page: segmented answers, card follows answer, green then approved",
    "review page: Changes needs a note; blocker rings the bar; copy blockers",
    "review page: picker filters by words and Enter jumps",
    "saved answers load and render; save failure shows amber",
    "unified page: group chips and total still count",
    "synthetic: h2 items, skip locks, approved hidden, blocked, question",
    "theme toggle sets data-theme, saves it, Auto clears it; survives blocked storage",
    "finished page: green bar and toast point back to the folder; Copy results returns after 1.5 s",
    "finished page: typing or moving after Copy results stays",
    "unfinished page: Copy results stays put and no back link",
    "blocker and reopened pills: later paints keep both pills and Add a note still opens",
]


def item(qid, title):
    return f'<div class="item" data-review-question="{qid}" data-title="{title}"><div class="ih">{title} <code>{qid}</code></div></div>'


UNIFIED = ('<!doctype html><html><head><title>U</title></head><body class="site unified" data-review-page="/demo/sm-unified/" '
           'data-review-h2="off"><header class="top"><div class="wrap"><h1>U</h1><p><span class="open-total">3</span> open items</p>'
           '</div></header><main class="wrap">'
           '<details class="grp" data-src="a.html"><summary><span class="gt">A</span><span class="gm">'
           '<span class="chip c-review" data-open-chip>2 open</span></span></summary><div class="gb">'
           + item("a.s1", "One") + item("a.s2", "Two") + '</div></details>'
           '<details class="grp" data-src="b.html"><summary><span class="gt">B</span><span class="gm">'
           '<span class="chip c-review" data-open-chip>1 open</span></span></summary><div class="gb">'
           + item("b.s1", "Three") + '</div></details></main>' + REVIEW + '</body></html>')

SYNTH = ('<!doctype html><html><head><title>Synth</title></head><body class="site" data-review-skip="on" data-review-approved="s1" '
         'data-review-blocked="s4=s2" data-build="1.2.3"><header class="top"><div class="wrap"><h1>Synth</h1><p>x</p></div></header>'
         '<main class="wrap"><h2>One</h2><p>a</p><h2>Two</h2><p>b</p><h2>Three</h2><p>c</p><h2>Four</h2><p>d</p>'
         '<h2 data-review-type="question">Q?</h2><p>e</p></main>' + REVIEW + '</body></html>')

# A review page whose items are [data-review-question] sections, so each section is the item's card.
SECTIONS = ('<!doctype html><html><head><title>Sections</title></head><body class="site" data-review-h2="off"><header class="top">'
            '<div class="wrap"><h1>Sections</h1><p>Four parts of a repo layout.</p></div></header><main class="wrap">'
            + "".join(f'<section data-review-question="r{n}" data-title="{n}. {t}"><h2>{n}. {t}</h2><p>{t}.</p></section>'
                      for n, t in ((1, "A module repo"), (2, "The web app"), (3, "The platform repos"), (4, "Shared config")))
            + '</main>' + REVIEW + '</body></html>')

# The same sections with r2 reopened, so one card carries the Reopened pill and another the Blocker pill.
PILLS = SECTIONS.replace('data-review-h2="off"', 'data-review-h2="off" data-review-reopen="r2=fixed in 1.2"', 1)

FINISHED = ('<!doctype html><html><head><title>Fin</title></head><body class="site" data-review-h2="off"><header class="top">'
            '<div class="wrap"><h1>Fin</h1></div></header><main class="wrap">'
            '<section data-review-question="a" data-title="A"><h2>A</h2></section>'
            '<section data-review-question="b" data-title="B"><h2>B</h2></section></main>' + REVIEW + '</body></html>')


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def write_pages(root):
    demo = root / "demo"
    backlog = (demo / "backlog.html").read_text()
    for n in (1, 2, 3):
        (demo / f"sm-backlog-{n}.html").write_text(backlog)
    for n in (1, 2, 3):
        (demo / f"sm-review-{n}.html").write_text(SECTIONS)
    (demo / "sm-saved.html").write_text(SECTIONS)
    (demo / "sm-pills.html").write_text(PILLS)
    (demo / "sm-unified").mkdir()
    (demo / "sm-unified" / "index.html").write_text(UNIFIED)
    (demo / "sm-synth.html").write_text(SYNTH)
    for n in (1, 2, 3):
        (demo / f"sm-fin-{n}.html").write_text(FINISHED)
    bare = re.sub(r'<script src="/_site/[a-z]+\.js[^"]*"[^>]*></script>', "", backlog)
    (demo / "sm-theme-1.html").write_text(bare)
    (demo / "sm-theme-2.html").write_text("<!doctype html><html><head></head><body class=site><p>x</p></body></html>")
    (demo / "sm-theme-3.html").write_text("<!doctype html><html><head></head><body class=site><header class=top></header></body></html>")
    # Saved answers for sm-saved.html, under the key review.js reads them from.
    spec = importlib.util.spec_from_file_location("serve_smoke", root / "_site" / "serve.py")
    assert spec and spec.loader
    serve = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(serve)
    prefix = json.loads((root / "site.json").read_text()).get("key_prefix", "review:")
    (root / "_saved").mkdir(exist_ok=True)
    (root / "_saved" / (serve.page_key(prefix + "/demo/sm-saved.html") + ".json")).write_text(json.dumps({"r1": {"v": "yes", "n": ""}}))


@pytest.fixture(scope="module")
def smoke(tmp_path_factory):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("Chrome or Chromium is not installed")
    tmp = tmp_path_factory.mktemp("smoke")
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
                            f"--user-data-dir={tmp / 'profile'}", "--virtual-time-budget=90000", "--dump-dom",
                            f"{base}/harness.html"], capture_output=True, text=True, timeout=180)
        m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
        assert m, r.stdout[-2000:] + r.stderr[-2000:]
        data = json.loads(html.unescape(m.group(1)))
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    assert "harness" not in data, data["harness"]
    return data


@pytest.mark.parametrize("name", SCENARIOS)
def test_review_smoke(smoke, name):
    assert smoke.get(name) == "ok", smoke.get(name, "did not run")

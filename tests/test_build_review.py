"""Tests for template/_site/build-review.py: open-question items carried into the unified page."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BUILD_REVIEW = ROOT / "template" / "_site" / "build-review.py"

PAGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Design</title></head>
<body class="site" data-review-approved="" data-review-reopen="">
<h2>Pick a layout</h2>
<p>Pick A or B.</p>
<h2 data-review-type="question" data-suggested="Nightly, UTC">When should the job run?</h2>
<p>Say the schedule.</p>
</body></html>
"""


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    (root / "_site").mkdir(parents=True)
    shutil.copy(BUILD_REVIEW, root / "_site" / "build-review.py")
    (root / "qdemo").mkdir()
    (root / "qdemo" / "_status.json").write_text(json.dumps({
        "design.html": {"state": "needs-you", "note": "A design with one choice and one question."},
    }))
    (root / "qdemo" / "design.html").write_text(PAGE_HTML)
    (root / "site.json").write_text(json.dumps({"folders": [{"id": "qdemo", "name": "Q Demo"}]}))
    return root


def build(site):
    mod = load_module(site / "_site" / "build-review.py", "build_review")
    mod.main("qdemo")
    return (site / "qdemo" / "review" / "index.html").read_text()


def test_question_item_carried_into_unified_page(site):
    out = build(site)
    assert 'data-review-type="question"' in out
    assert 'data-suggested="Nightly, UTC"' in out
    assert 'data-review-question="design.s2"' in out


def test_question_item_excluded_from_open_count(site, capsys):
    build(site)
    printed = capsys.readouterr().out
    # one Yes/No/Changes item (s1) open; the question (s2) must not inflate the open count.
    assert "open=1" in printed

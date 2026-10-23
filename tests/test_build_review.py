"""Tests for template/_site/build-review.py: open-question items carried into the unified page."""

import importlib.util
import json
import re
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


BLOCKED_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Checks</title></head>
<body class="site" data-review-blocked="s3=s1">
<h2>Sign in works</h2>
<p>Sign in.</p>
<h2>Profile saves</h2>
<p>Save it.</p>
<h2>Sign out works</h2>
<p>Needs sign in first.</p>
</body></html>
"""


def build_blocked(site):
    (site / "qdemo" / "_status.json").write_text(json.dumps({
        "design.html": {"state": "needs-you", "note": "A design with one choice and one question."},
        "checks.html": {"state": "needs-you", "note": "Three checks, one blocked."},
    }))
    (site / "qdemo" / "checks.html").write_text(BLOCKED_HTML)
    return build(site)


def test_blocked_items_carried_into_unified_page(site):
    out = build_blocked(site)
    assert 'data-review-blocked="checks.s3=checks.s1"' in out


def test_blocked_items_not_counted_open(site, capsys):
    out = build_blocked(site)
    # design: s1 open (s2 is a question); checks: s1 and s2 open, s3 blocked.
    assert "open=3" in capsys.readouterr().out
    assert '<span class="chip c-review" data-open-chip>2 open</span>' in out
    assert '<span class="chip c-review" data-open-chip>1 open</span>' in out


def test_header_total_is_marked_for_live_updates(site):
    out = build_blocked(site)
    assert '<span class="open-total">3</span> open items from 2 pages' in out


CHOICES_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Backlog</title></head>
<body class="site" data-review-options="start:Start,hold:Hold" data-review-default="hold" data-review-approved="s1">
<h2>Export as PDF</h2>
<p>Two days.</p>
<h2>Dark theme</h2>
<p>One day.</p>
<h2>Single sign-on</h2>
<p>Needs a provider first.</p>
</body></html>
"""


def build_choices(site):
    (site / "qdemo" / "_status.json").write_text(json.dumps({
        "design.html": {"state": "needs-you", "note": "A design with one choice and one question."},
        "backlog.html": {"state": "needs-you", "note": "Three backlog items."},
    }))
    (site / "qdemo" / "backlog.html").write_text(CHOICES_HTML)
    return build(site)


def test_choice_items_carry_their_options_and_default(site):
    out = build_choices(site)
    for sid in ("s1", "s2", "s3"):
        assert re.search(r'<div class="item" data-review-question="backlog\.' + sid + r'"[^>]*'
                         r'data-review-options="start:Start,hold:Hold" data-review-default="hold"', out)
    # the design page's items keep Yes / No / Changes: no options on them
    assert not re.search(r'data-review-question="design\.s1"[^>]*data-review-options', out)


def test_choice_items_never_count_as_open_or_approved(site, capsys):
    out = build_choices(site)
    # design s1 is the only open item; backlog items are choices (s1 listed as approved is ignored).
    assert "open=1 approved=0" in capsys.readouterr().out
    assert '<span class="open-total">1</span> open items from 2 pages' in out
    assert "backlog.s1" not in re.search(r'data-review-approved="([^"]*)"', out).group(1)
    # the backlog group's chip shows the choice counts (every item at its default), not "N open"
    assert '<span class="chip" data-open-chip data-choice-chip>0 start · 3 hold</span>' in out


def test_item_level_options_override_the_page(site):
    (site / "qdemo" / "design.html").write_text(PAGE_HTML.replace(
        "<h2>Pick a layout</h2>", '<h2 data-review-options="a:Option A,b:Option B" data-review-default="a">Pick a layout</h2>'))
    out = build(site)
    assert re.search(r'data-review-question="design\.s1"[^>]*data-review-options="a:Option A,b:Option B" data-review-default="a"', out)


WRAPPED_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Wrapped</title></head>
<body class="site">
<header class="top"><h1>Wrapped</h1></header>
<main class="wrap">
<h2>One</h2>
<p>First section.</p>
<div class="box">
<h2>Two</h2>
<p>Second section.</p>
</div>
</main>
<footer>footer</footer>
</body></html>
"""


def test_plain_page_wrapper_tags_stay_inside_their_items(site):
    """The last <h2> section runs to the end of the body; the page's </main> must not close the unified page's."""
    (site / "qdemo" / "_status.json").write_text(json.dumps({"wrapped.html": {"state": "needs-you", "note": "x"}}))
    (site / "qdemo" / "wrapped.html").write_text(WRAPPED_HTML)
    out = build(site)
    assert out.count("<main") == 1 and out.count("</main>") == 1
    assert out.index("</main>") > out.rindex("</details>")
    assert out.count("<div") == out.count("</div>")

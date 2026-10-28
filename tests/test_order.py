"""Index card order (gen-index.py order_pages()): by number and _status.json order, never by change time."""

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


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(html_example(d), root / d)
    shutil.copy(ROOT / "example" / "site.json", root / "site.json")
    return root


@pytest.fixture()
def gi(site):
    spec = importlib.util.spec_from_file_location("gen_index_order", site / "gen-index.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pg(key, title, mtime=0, priority=50):
    return dict(key=key, title=title, mtime=mtime, priority=priority)


def keys(gi, pages, manifest=()):
    return [p["key"] for p in gi.order_pages(pages, list(manifest))]


def test_leading_numbers_sort_naturally(gi):
    pages = [pg("a.html", "10. x", 3), pg("b.html", "2. y", 1), pg("c.html", "1. z", 2)]
    assert keys(gi, pages) == ["c.html", "b.html", "a.html"]


def test_numbered_file_names_sort_naturally_not_by_change_time(gi):
    pages = [pg(f"design-review-{n}-x.html", f"Review {n}", mtime=100 - n) for n in (7, 10, 2, 1)]
    assert keys(gi, pages) == ["design-review-1-x.html", "design-review-2-x.html", "design-review-7-x.html", "design-review-10-x.html"]


def test_unnumbered_pages_keep_manifest_order(gi):
    pages = [pg("zeta.html", "Zeta", 9), pg("alpha.html", "Alpha", 1), pg("mid.html", "Mid", 5)]
    assert keys(gi, pages, ["mid.html", "zeta.html", "alpha.html"]) == ["mid.html", "zeta.html", "alpha.html"]


def test_a_series_stays_together_where_its_first_page_sits(gi):
    man = ["design-s2-a.html", "history/", "design-s3-b.html", "design-review-1-c.html", "design-review-2-d.html"]
    pages = [pg("design-review-2-d.html", "R2"), pg("design-s3-b.html", "S3"), pg("history/", "History"),
             pg("design-review-1-c.html", "R1"), pg("design-s2-a.html", "S2")]
    assert keys(gi, pages, man) == ["design-s2-a.html", "design-s3-b.html", "history/", "design-review-1-c.html", "design-review-2-d.html"]


def test_priority_then_the_unified_page_come_first(gi):
    pages = [pg("b.html", "2. b"), pg("review/", "Everything"), pg("a.html", "1. a", priority=60)]
    assert keys(gi, pages) == ["review/", "b.html", "a.html"]


def test_ties_are_stable(gi):
    pages = [pg("x.html", "Same"), pg("y.html", "Same")]
    assert keys(gi, pages, ["y.html", "x.html"]) == ["y.html", "x.html"]
    assert keys(gi, pages) == ["x.html", "y.html"]


def test_folder_index_lists_numbered_pages_in_order_after_an_edit(site):
    folder = site / "demo"
    manifest = json.loads((folder / "_status.json").read_text())
    for name, title in (("p-a.html", "10. x"), ("p-b.html", "2. y"), ("p-c.html", "1. z")):
        (folder / name).write_text(f"<!doctype html><html><head><title>{title}</title></head><body class=site><p>{title}</p></body></html>")
        manifest[name] = {"state": "needs-you", "note": title}
    (folder / "_status.json").write_text(json.dumps(manifest))
    for _ in range(2):
        r = subprocess.run([sys.executable, str(site / "gen-index.py")], cwd=site, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        order = [k for k in re.findall(r'data-key="demo/(p-[abc]\.html)"', (folder / "index.html").read_text())]
        assert order == ["p-c.html", "p-b.html", "p-a.html"]
        (folder / "p-a.html").touch()

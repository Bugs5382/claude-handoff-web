"""The React app: every page file gets its shell, and a page draws in a real browser."""
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from test_review_choices import find_chrome

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "template" / "_site"
sys.path.insert(0, str(SITE))

import pagefile  # noqa: E402
import samples  # noqa: E402

ROOTS = {}


def site_root(host):
    return ROOTS[host]


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(SITE, root / "_site")
    (root / "site.json").write_text(json.dumps({"folders": [{"id": "demo", "name": "Demo"}]}))
    samples.load(str(root / "demo"), route="app")
    proc = subprocess.Popen([sys.executable, "-u", str(root / "_site" / "serve.py"), "0", "--directory", str(root)],
                            stderr=subprocess.PIPE, text=True)
    line = proc.stderr.readline()
    host = line.split("http://")[1].split("/")[0]
    ROOTS[host] = root
    yield host
    proc.terminate()
    proc.wait(timeout=10)


def test_a_page_file_gets_the_app_shell(site):
    assert "app/app.js" in urllib.request.urlopen(f"http://{site}/demo/sample-review").read().decode()


def test_the_built_app_is_in_the_template():
    assert (SITE / "app" / "app.js").stat().st_size > 1000


def test_a_page_draws_in_a_browser(site):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("no Chrome")
    dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000", "--dump-dom",
                          f"http://{site}/demo/sample-review"], capture_output=True, text=True, timeout=60).stdout
    assert dom.count("data-review-question=") == 5, dom[:400]
    assert "Sample: a plain review" in dom and "rvbar" in dom and "Send to app" in dom


def test_a_blocker_the_agent_replied_to_clears_in_the_browser(site):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("no Chrome")
    page = Path(site_root(site)) / "demo" / "sample-review.json"
    pagefile.save_answers(str(page), {"s2": {"answer": "", "note": "Vendor contract missing"}}, by="me", now="2026-10-26T07:42:10-04:00")
    blocker = {"kind": "blocker", "to": "app", "items": ["s2"], "file": "0-b.json"}
    pagefile.add_submission(str(page), blocker, now="2026-10-26T08:05:44-04:00")
    before = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000", "--dump-dom",
                             f"http://{site}/demo/sample-review"], capture_output=True, text=True, timeout=60).stdout
    assert "is-blocker" in before and "Vendor contract missing" in before, before[:400]
    pagefile.reply(str(page), "s2", "app", "Added the contract.", now="2026-10-26T08:20:02-04:00")
    dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000", "--dump-dom",
                          f"http://{site}/demo/sample-review"], capture_output=True, text=True, timeout=60).stdout
    assert "is-blocker" not in dom, "a handled blocker is no longer flagged"
    assert ">Vendor contract missing</textarea>" not in dom, "the note box is empty again"
    assert "Updated: answer again" in dom and "Added the contract." in dom

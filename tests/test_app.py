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

import samples  # noqa: E402


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(SITE, root / "_site")
    (root / "site.json").write_text(json.dumps({"folders": [{"id": "demo", "name": "Demo"}]}))
    samples.load(str(root / "demo"), route="app")
    proc = subprocess.Popen([sys.executable, "-u", str(root / "_site" / "serve.py"), "0", "--directory", str(root)],
                            stderr=subprocess.PIPE, text=True)
    line = proc.stderr.readline()
    yield line.split("http://")[1].split("/")[0]
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

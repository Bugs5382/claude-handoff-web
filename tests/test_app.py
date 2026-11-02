"""The React app: the shell is opt-in, and the first page draws from a page file in a real browser."""
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
    (root / "site.json").write_text(json.dumps({"renderer": "app", "folders": [{"id": "demo", "name": "Demo"}]}))
    samples.load(str(root / "demo"), route="app")
    proc = subprocess.Popen([sys.executable, "-u", str(root / "_site" / "serve.py"), "0", "--directory", str(root)],
                            stderr=subprocess.PIPE, text=True)
    line = proc.stderr.readline()
    yield line.split("http://")[1].split("/")[0]
    proc.terminate()
    proc.wait(timeout=10)


def test_an_install_without_the_setting_keeps_the_old_shell():
    assert "render.js" in (SITE / "page.html").read_text() and "app/app.js" in (SITE / "app.html").read_text()


def test_the_app_shell_is_served_when_the_site_asks_for_it(site):
    assert "app/app.js" in urllib.request.urlopen(f"http://{site}/demo/sample-review").read().decode()


def test_one_page_can_try_the_app_on_a_site_without_the_setting(site, tmp_path):
    config = tmp_path / "site" / "site.json"
    config.write_text(json.dumps({"folders": [{"id": "demo", "name": "Demo"}]}))
    assert "render.js" in urllib.request.urlopen(f"http://{site}/demo/sample-review").read().decode()
    assert "app/app.js" in urllib.request.urlopen(f"http://{site}/demo/sample-review?app=1").read().decode()


def test_the_built_app_is_in_the_template():
    assert (SITE / "app" / "app.js").stat().st_size > 1000


def test_the_first_page_draws_in_a_browser(site):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("no Chrome")
    dom = subprocess.run([chrome, "--headless", "--no-sandbox", "--disable-gpu", "--virtual-time-budget=4000", "--dump-dom",
                          f"http://{site}/demo/sample-review"], capture_output=True, text=True, timeout=60).stdout
    assert dom.count("data-review-question=") == 5, dom[:400]
    assert "Sample: a plain review" in dom and "rvbar" in dom and "Send to app" in dom

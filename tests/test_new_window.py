"""Which links open in a new window (siteLinks in live.js), run in node: page links get target=_blank,
while # anchors, the picture viewer, downloads and links with their own target keep their behaviour."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIVE_JS = ROOT / "template" / "_site" / "live.js"
LINK_TEST = ROOT / "tests" / "js" / "new_window.test.js"


def test_new_window_rules():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(LINK_TEST), str(LIVE_JS)], capture_output=True, text=True, timeout=30)
    lines = out.stdout.splitlines()
    assert sum(ln.startswith("ok ") for ln in lines) >= 17, out.stdout + out.stderr
    assert out.returncode == 0, out.stdout + out.stderr

"""The bottom bar's counting rules (rvCount in review.js), run in node: what counts as answered, when the
bar turns green or APPROVED, and how choices pages count picks."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REVIEW_JS = ROOT / "template" / "_site" / "review.js"
COUNT_TEST = ROOT / "tests" / "js" / "rv_count.test.js"


def test_rv_count_rules():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(COUNT_TEST), str(REVIEW_JS)], capture_output=True, text=True, timeout=30)
    lines = out.stdout.splitlines()
    assert sum(ln.startswith("ok ") for ln in lines) >= 12, out.stdout + out.stderr
    assert out.returncode == 0, out.stdout + out.stderr

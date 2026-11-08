"""The inline Copy button's markup (inline() in web/src/lib/text.ts), run in node."""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEXT_TS = ROOT / "web" / "src" / "lib" / "text.ts"
TEST = ROOT / "tests" / "js" / "inline_copy.test.mjs"
CLICK_TEST = ROOT / "tests" / "js" / "copy_click.test.mjs"
COPY_TS = ROOT / "web" / "src" / "lib" / "copy.ts"


def test_inline_copy_markup():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(TEST), str(TEXT_TS)], capture_output=True, text=True, timeout=30)
    assert sum(ln.startswith("ok ") for ln in out.stdout.splitlines()) >= 10, out.stdout + out.stderr
    assert out.returncode == 0, out.stdout + out.stderr


def test_inline_copy_click():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(CLICK_TEST), str(COPY_TS)], capture_output=True, text=True, timeout=30)
    assert sum(ln.startswith("ok ") for ln in out.stdout.splitlines()) == 5, out.stdout + out.stderr
    assert out.returncode == 0, out.stdout + out.stderr

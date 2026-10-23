"""Tests for install.sh: the example folders land as folders, and options apply on top of the example site.json."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def install(target, *args):
    r = subprocess.run(["bash", str(ROOT / "install.sh"), str(target), *args], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads((target / "site.json").read_text())


def test_example_folders_are_copied_as_folders(tmp_path):
    site = tmp_path / "site"
    cfg = install(site, "--example")
    assert [f["id"] for f in cfg["folders"]] == ["demo", "guide"]
    assert (site / "demo" / "backlog.html").is_file()
    assert (site / "demo" / "img").is_dir()
    assert (site / "guide" / "page-types.md").is_file()
    assert not (site / "backlog.html").exists() and not (site / "img").exists() and not (site / "_status.json").exists()
    assert "backlog.html" in json.loads((site / "demo" / "_status.json").read_text())


def test_example_with_owner_keeps_the_example_site(tmp_path):
    site = tmp_path / "site"
    cfg = install(site, "--example", "--owner", "Sam", "--port", "8123")
    assert cfg["owner"] == "Sam"
    assert cfg["title"] == "Pages for Sam"
    assert cfg["port"] == 8123
    assert [f["id"] for f in cfg["folders"]] == ["demo", "guide"]
    assert cfg["order"] == ["demo", "guide"]
    assert cfg["timezone"] == "UTC"


def test_example_with_folders_adds_them_next_to_the_example_ones(tmp_path):
    site = tmp_path / "site"
    cfg = install(site, "--example", "--folders", "ops:Operator:Coordination")
    assert [f["id"] for f in cfg["folders"]] == ["demo", "guide", "ops"]
    assert cfg["order"] == ["demo", "guide", "ops"]
    assert cfg["owner"] == "Alex"
    assert (site / "ops" / "_status.json").is_file()


def test_without_example_options_build_site_json(tmp_path):
    site = tmp_path / "site"
    cfg = install(site, "--owner", "Sam", "--folders", "ops:Operator:Coordination")
    assert cfg["owner"] == "Sam" and cfg["title"] == "Pages for Sam"
    assert [f["id"] for f in cfg["folders"]] == ["ops"]
    assert not (site / "demo").exists()

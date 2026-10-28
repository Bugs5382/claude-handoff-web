"""Which browser the headless suites use: chrome-headless-shell first (no app bundle, so no Dock icon on a Mac),
then a full Chrome or Chromium."""

import stat

import test_review_choices
from test_review_choices import find_chrome


def fake(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def isolate(monkeypatch, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("CHROME", raising=False)
    monkeypatch.setattr(test_review_choices, "MAC_CHROME", str(tmp_path / "no-chrome-app"))
    return bin_dir


def test_prefers_chrome_headless_shell_on_path(monkeypatch, tmp_path):
    bin_dir = isolate(monkeypatch, tmp_path)
    fake(bin_dir / "google-chrome")
    shell = fake(bin_dir / "chrome-headless-shell")
    assert find_chrome() == shell


def test_finds_the_newest_shell_in_the_puppeteer_cache(monkeypatch, tmp_path):
    bin_dir = isolate(monkeypatch, tmp_path)
    fake(bin_dir / "google-chrome")
    cache = tmp_path / "home" / ".cache" / "puppeteer" / "chrome-headless-shell"
    fake(cache / "mac_arm-99.0.4844.51" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell")
    newest = fake(cache / "mac_arm-131.0.6778.85" / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell")
    assert find_chrome() == newest


def test_chrome_env_wins_and_full_chrome_is_the_fallback(monkeypatch, tmp_path):
    bin_dir = isolate(monkeypatch, tmp_path)
    full = fake(bin_dir / "google-chrome")
    assert find_chrome() == full
    fake(bin_dir / "chrome-headless-shell")
    mine = fake(tmp_path / "my-chrome")
    monkeypatch.setenv("CHROME", mine)
    assert find_chrome() == mine

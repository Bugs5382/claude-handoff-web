"""review.js answer choices in a real browser: a page that declares its own choices and a default.

Drives headless Chrome against a real serve.py. A harness page loads the example backlog page in a
same-origin frame, clicks and types like the owner would, and writes what it saw into the DOM, which
Chrome dumps. Skipped when no Chrome or Chromium is installed.
"""

import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def find_chrome():
    for c in (os.environ.get("CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", MAC_CHROME):
        if c and (shutil.which(c) or os.path.isfile(c)):
            return shutil.which(c) or c
    return None


HARNESS = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>harness</title></head><body>
<iframe id="f" style="width:1000px;height:800px"></iframe>
<pre id="out">pending</pre>
<script>
const out = {};
const f = document.getElementById("f");
const d = () => f.contentDocument, w = () => f.contentWindow;
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function until(cond, what) {
  for (let i = 0; i < 400; i++) { try { if (cond()) return; } catch (e) {} await sleep(50); }
  throw new Error("timed out waiting for " + what);
}
function load(url) { return new Promise(r => { f.onload = r; f.src = url; }); }
function snap() {
  const s = {};
  for (const box of d().querySelectorAll(".rv")) {
    const pressed = (box.querySelector(".seg button[aria-pressed=true]") || { dataset: {} }).dataset.v || "";
    s[box.id] = { checked: box.dataset.choice || pressed, pressed,
                  def: (box.querySelector(".seg button.def") || { dataset: {} }).dataset.v || "",
                  values: Array.from(box.querySelectorAll(".seg button")).map(b => b.dataset.v),
                  status: (box.closest(".rvcard") || box).querySelector(".rvhead .st").textContent,
                  note: (box.querySelector("textarea") || {}).value || "",
                  placeholder: (box.querySelector("textarea") || {}).placeholder || "",
                  noteLabel: (box.querySelector(".notel > span") || {}).textContent || "", blocker: !!box.querySelector(".blocker-btn"),
                  need: !!box.querySelector(".need") };
  }
  return { items: s, bar: d().querySelector(".rvbar .cnt").textContent, results: w().siteReview.results() };
}
async function ready() { await until(() => w().siteReview && d().querySelector(".rvbar .cnt").textContent, "review.js"); }
async function saved() { await until(() => !w().siteReview.unsaved(), "the save"); }
(async () => {
  const mode = new URLSearchParams(location.search).get("mode");
  if (mode === "act") {
    await load("/demo/backlog.html"); await ready();
    out.first = snap();
    out.firstBox = await (await fetch(w().siteReview.saveUrl, { cache: "no-store" })).status;
    d().querySelector("#rv-s1 .seg button[data-v=start]").click();
    const ta = d().querySelector("#rv-s2 textarea");
    ta.value = "Not before Q3"; ta.dispatchEvent(new Event("input", { bubbles: true }));
    await sleep(100); await saved();
    out.box = await (await fetch(w().siteReview.saveUrl, { cache: "no-store" })).json();
    await load("/demo/backlog.html?again"); await ready();
    out.reloaded = snap();
  } else if (mode === "unified") {
    await load("/demo/review/"); await ready();
    const grp = () => d().querySelector('details.grp[data-src="backlog.html"]');
    const chip = () => grp().querySelector("[data-open-chip]").textContent;
    out.chip = chip();
    out.total = d().querySelector(".open-total").textContent;
    out.before = snap();
    d().querySelector("#rv-backlog\\.s3 .seg button[data-v=start]").click();
    await sleep(100); await saved();
    out.chipAfter = chip();
    out.groupResults = w().siteReview.results(grp());
  } else {
    await load("/demo/backlog.html"); await ready();
    out.newDefault = snap();
    await load("/demo/design-review.html"); await ready();
    out.yesNo = snap();
    await load("/demo/signoff-checklist.html"); await ready();
    out.checklist = snap();
    await load("/demo/review/"); await ready();
    out.unifiedChecklist = snap();
  }
})().catch(e => { out.error = String(e && e.stack || e); })
  .finally(() => { document.getElementById("out").textContent = JSON.stringify(out); });
</script></body></html>
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    chrome = find_chrome()
    if not chrome:
        pytest.skip("Chrome or Chromium is not installed")
    tmp = tmp_path_factory.mktemp("choices")
    root = tmp / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(ROOT / "example" / d, root / d)
    shutil.copy(ROOT / "example" / "site.json", root / "site.json")
    (root / "harness.html").write_text(HARNESS)
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(root / "_site" / "serve.py"), str(port), "--bind", "127.0.0.1",
                             "--directory", str(root)], stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/", timeout=1)
                break
            except OSError:
                time.sleep(0.05)

        def run(mode):
            profile = tmp / f"profile-{mode}"
            r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                                f"--user-data-dir={profile}", "--virtual-time-budget=30000", "--dump-dom",
                                f"{base}/harness.html?mode={mode}"], capture_output=True, text=True, timeout=120)
            m = re.search(r'<pre id="out">(.*?)</pre>', r.stdout, re.S)
            assert m, r.stdout[-2000:] + r.stderr[-2000:]

            data = json.loads(html.unescape(m.group(1)))
            assert "error" not in data, data["error"]
            return data

        built = subprocess.run([sys.executable, str(root / "_site" / "build-review.py"), "demo"], cwd=root, capture_output=True, text=True)
        assert built.returncode == 0, built.stderr
        unified = run("unified")
        acted = run("act")
        page = root / "demo" / "backlog.html"
        page.write_text(page.read_text().replace('data-review-default="hold"', 'data-review-default="start"'))
        after = run("read")
        yield acted, after, unified
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def test_untouched_items_show_the_default(browser):
    first = browser[0]["first"]
    assert browser[0]["firstBox"] == 404, "nothing is saved just by opening the page"
    for sid in ("s1", "s2", "s3"):
        it = first["items"][f"rv-{sid}"]
        assert it["values"] == ["start", "hold"]
        assert it["checked"] == "hold" and it["def"] == "hold"
        assert it["pressed"] == "", "the default is marked, not pressed"
        assert it["status"] == "Not picked · Hold (default)"
        assert it["noteLabel"] == "Comments (optional)"
        assert not it["blocker"] and not it["need"]
    assert first["bar"] == "0 of 3 picked · 0 start · 3 hold"


def test_only_what_the_owner_changed_is_saved(browser):
    assert browser[0]["box"] == {"s1": {"v": "start", "n": ""}, "s2": {"v": "", "n": "Not before Q3"}}


def test_choice_and_comment_survive_reload(browser):
    r = browser[0]["reloaded"]
    assert r["items"]["rv-s1"]["checked"] == "start" and r["items"]["rv-s1"]["pressed"] == "start"
    assert r["items"]["rv-s1"]["status"] == "Start"
    assert r["items"]["rv-s2"]["checked"] == "hold" and r["items"]["rv-s2"]["note"] == "Not before Q3"
    assert r["items"]["rv-s2"]["status"] == "Not picked · Hold (default)"
    assert r["items"]["rv-s3"]["checked"] == "hold"
    assert r["bar"] == "1 of 3 picked · 1 start · 2 hold"


def test_copy_results_lists_each_choice(browser):
    assert browser[0]["reloaded"]["results"] == (
        "Review: Demo app backlog (/demo/backlog.html)\n"
        "- [s1] START: Export reports as PDF\n"
        "- [s2] HOLD: Dark theme\n"
        "    Note: Not before Q3\n"
        "- [s3] HOLD: Single sign-on\n"
        "\n"
        "1 start · 2 hold\n")


def test_a_new_default_applies_to_items_nobody_picked(browser):
    r = browser[1]["newDefault"]
    assert r["items"]["rv-s1"]["checked"] == "start"
    assert r["items"]["rv-s2"]["checked"] == "start", "a comment alone doesn't pin the old default"
    assert r["items"]["rv-s3"]["checked"] == "start"
    assert r["items"]["rv-s2"]["status"] == "Not picked · Start (default)"
    assert r["bar"] == "1 of 3 picked · 3 start · 0 hold"


def test_pages_without_choices_keep_yes_no_changes(browser):
    r = browser[1]["yesNo"]
    it = r["items"]["rv-s1"]
    assert it["values"] == ["yes", "no", "chg"]
    assert it["checked"] == "" and it["def"] == "" and it["status"] == "Open"
    assert it["placeholder"] == "Notes (required for Changes)"
    assert it["blocker"] and it["need"]
    assert r["bar"].startswith("0 of 3 answered")
    assert "Not approved yet: 0 of 3 are Yes." in r["results"]


def test_unified_page_keeps_each_groups_choices(browser):
    u = browser[2]
    assert u["chip"] == "0 start · 3 hold"
    # design review: 3 open (its question doesn't count); checklist: 2 open, 1 blocked. The backlog adds none.
    assert u["total"] == "5"
    assert u["before"]["items"]["rv-backlog.s1"]["values"] == ["start", "hold"]
    # the checklist group turns on Skipped for the whole unified page; the backlog keeps only its own choices
    assert u["before"]["items"]["rv-design-review.s1"]["values"] == ["yes", "no", "chg", "skip"]
    assert u["before"]["bar"].endswith("0 start · 3 hold · 1 question unanswered")
    assert u["chipAfter"] == "1 start · 2 hold"
    assert u["groupResults"] == (
        "Review: Demo app backlog (/demo/backlog.html)\n"
        "- [backlog.s1] HOLD: Demo app backlog: Export reports as PDF\n"
        "- [backlog.s2] HOLD: Demo app backlog: Dark theme\n"
        "- [backlog.s3] START: Demo app backlog: Single sign-on\n"
        "\n"
        "1 start · 2 hold\n"
        "  backlog: 1 start · 2 hold\n")


def test_blocked_item_keeps_its_blocked_status_once_locked(browser):
    """A blocked item is locked like a skipped one, but its status still names what blocks it."""
    page, unified = browser[1]["checklist"]["items"], browser[1]["unifiedChecklist"]["items"]
    assert page["rv-t3"]["status"] == "Blocked by t2 (sign-in must pass first)"
    assert unified["rv-signoff-checklist.t3"]["status"] == "Blocked by signoff-checklist.t2 (sign-in must pass first)"
    assert page["rv-t1"]["status"] == "Open"

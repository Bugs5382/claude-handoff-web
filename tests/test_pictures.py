"""Pictures open in one reused popup window (live.js), and the builders keep picture links intact."""

import html
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIVE_JS = ROOT / "template" / "_site" / "live.js"
BUILD_REVIEW = ROOT / "template" / "_site" / "build-review.py"

PAGE_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Design</title></head>
<body class="site">
<h2>Pick a layout</h2>
<p><a href="img/option-a.png" target="_blank" rel="noopener"><img src="img/option-a.png" alt="Option A"></a></p>
</body></html>
"""


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_unified_page_keeps_picture_links(tmp_path):
    root = tmp_path / "site"
    (root / "_site").mkdir(parents=True)
    shutil.copy(BUILD_REVIEW, root / "_site" / "build-review.py")
    (root / "pdemo").mkdir()
    (root / "pdemo" / "_status.json").write_text(json.dumps({"design.html": {"state": "needs-you", "note": "One picture."}}))
    (root / "pdemo" / "design.html").write_text(PAGE_HTML)
    (root / "site.json").write_text(json.dumps({"folders": [{"id": "pdemo", "name": "P Demo"}]}))
    load_module(root / "_site" / "build-review.py", "build_review_pics").main("pdemo")
    out = (root / "pdemo" / "review" / "index.html").read_text()
    m = re.search(r'srcdoc="([^"]*)"', out)
    assert m, "a picture is bulky, so the item's details render in a frame"
    doc = html.unescape(m.group(1))
    assert '<base href="/pdemo/"' in doc
    assert '<a href="img/option-a.png"' in doc
    assert '<img src="img/option-a.png" alt="Option A">' in doc
    assert "/_site/review.js" in out


# A minimal browser stand-in: enough of window/document for live.js to load in page mode, plus
# fake links, pictures and a fake popup window that records what is written into it.
HARNESS = r"""
const fs = require("fs"), vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const listeners = {};
const opened = [];
let popup = null, blocked = false;
function fakePopup() {
  const ids = {};
  const doc = {
    html: "", title: "",
    open() { this.html = ""; }, write(s) { this.html += s; },
    close() { for (const m of this.html.matchAll(/id="([^"]+)"/g)) ids[m[1]] = { id: m[1], src: "", alt: "", href: "", textContent: "" }; },
    getElementById(id) { return ids[id] || null; },
  };
  return { document: doc, focused: 0, focus() { this.focused++; }, closed: false };
}
const document = {
  currentScript: { getAttribute: n => (n === "data-mode" ? "page" : null) },
  hidden: true, readyState: "complete",
  addEventListener(t, f) { (listeners[t] = listeners[t] || []).push(f); },
  querySelector() { return null; }, querySelectorAll() { return []; }, getElementById() { return null; },
  createElement(tag) { return { tagName: tag.toUpperCase() }; },
  head: { added: [], appendChild(el) { this.added.push(el); } },
  documentElement: { getAttribute() { return null; } },
};
const store = () => {
  const m = {};
  return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); }, removeItem: k => { delete m[k]; } };
};
const window = {
  open(url, name, feats) { opened.push({ url, name, feats }); if (blocked) return null; if (!popup) popup = fakePopup(); return popup; },
};
const ctx = {
  window, document, URL, console,
  location: { pathname: "/demo/design.html", href: "http://h/demo/design.html", origin: "http://h" },
  localStorage: store(), sessionStorage: store(),
  setTimeout() {}, setInterval() {}, clearInterval() {}, requestAnimationFrame() {},
  addEventListener() {}, fetch() { return new Promise(() => {}); },
};
ctx.window.document = document;
vm.createContext(ctx);
vm.runInContext(src, ctx);

function link(href, alt, withImg = true) {
  const img = withImg ? { tagName: "IMG", alt, getAttribute: n => (n === "alt" ? alt : null) } : null;
  const a = { tagName: "A", href, hasAttribute: () => false, getAttribute: n => (n === "href" ? href : null),
              querySelector: s => (s === "img" ? img : null) };
  a.closest = s => (/^a\b/.test(s) ? a : null);
  if (img) img.closest = a.closest;
  return img || a;
}
function click(target, mods = {}) {
  const ev = { type: "click", target, button: 0, metaKey: false, ctrlKey: false, shiftKey: false, altKey: false,
               defaultPrevented: false, prevented: false, ...mods };
  ev.preventDefault = () => { ev.prevented = true; ev.defaultPrevented = true; };
  for (const f of listeners.click || []) f(ev);
  return ev;
}
const r = {};
r.plain = click(link("http://h/demo/img/a.png", "Option A")).prevented;
const el = id => popup?.document.getElementById(id) ?? null;
r.first = { opens: opened.length, name: opened[0]?.name, focused: popup?.focused, src: el("pic")?.src, caption: el("cap")?.textContent };
const firstPopup = popup;
r.second = click(link("http://h/demo/img/b.webp", "Option B")).prevented;
r.after = { opens: opened.length, name: opened[1]?.name, same: !!popup && popup === firstPopup, focused: popup?.focused,
            src: el("pic")?.src, caption: el("cap")?.textContent, writes: (popup?.document.html.match(/<!doctype/gi) || []).length };
const before = opened.length;
r.meta = click(link("http://h/demo/img/c.png", "C"), { metaKey: true }).prevented;
r.ctrl = click(link("http://h/demo/img/c.png", "C"), { ctrlKey: true }).prevented;
r.middle = click(link("http://h/demo/img/c.png", "C"), { button: 1 }).prevented;
r.notPicture = click(link("http://h/demo/other.html", "x")).prevented;
r.noImg = click(link("http://h/demo/img/c.png", "", false)).prevented;
r.otherOpens = opened.length - before;
blocked = true; popup = null;
r.blocked = click(link("http://h/demo/img/d.jpg", "D")).prevented;
r.themeScript = document.head.added.map(e => e.src);
console.log(JSON.stringify(r));
"""


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    harness = tmp_path_factory.mktemp("pictures") / "harness.js"
    harness.write_text(HARNESS)
    out = subprocess.run([node, str(harness), str(LIVE_JS)], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_picture_click_opens_one_named_popup(run):
    assert run["plain"] is True
    assert run["first"]["opens"] == 1
    assert run["first"]["name"] == "picture"
    assert run["first"]["src"] == "http://h/demo/img/a.png"
    assert run["first"]["caption"] == "Option A"
    assert run["first"]["focused"] == 1


def test_next_picture_swaps_the_same_popup(run):
    assert run["second"] is True
    assert run["after"]["name"] == "picture"
    assert run["after"]["same"] is True
    assert run["after"]["src"] == "http://h/demo/img/b.webp"
    assert run["after"]["caption"] == "Option B"
    assert run["after"]["focused"] == 2
    assert run["after"]["writes"] == 1, "the popup page is written once, then only the picture changes"


def test_modified_clicks_and_other_links_keep_browser_behaviour(run):
    assert run["meta"] is False
    assert run["ctrl"] is False
    assert run["middle"] is False
    assert run["notPicture"] is False
    assert run["noImg"] is False
    assert run["otherOpens"] == 0


def test_blocked_popup_falls_back_to_the_plain_link(run):
    assert run["blocked"] is False


def test_pages_without_theme_js_get_it_from_live_js(run):
    assert len(run["themeScript"]) == 1 and run["themeScript"][0].startswith("/_site/theme.js")

// Which links open in a new window (siteLinks in live.js, between the new-window markers). Run by
// tests/test_new_window.py: node tests/js/new_window.test.js template/_site/live.js
const fs = require("fs"), assert = require("assert"), vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const m = src.match(/\/\/ new-window:begin([\s\S]*?)\/\/ new-window:end/);
assert.ok(m, "new-window block not found in live.js");
const ctx = { window: {}, URL }; vm.createContext(ctx); vm.runInContext(m[1], ctx);
const links = ctx.window.siteLinks;
assert.strictEqual(typeof links.opensNewWindow, "function");
assert.strictEqual(typeof links.hook, "function");

const here = new URL("http://127.0.0.1:5390/ops/review/?x=1");
function link(href, attrs = {}, img = false) {
  const a = { attrs: Object.assign({ href }, attrs), href: new URL(href, here).href, img };
  a.getAttribute = k => (k in a.attrs ? a.attrs[k] : null);
  a.hasAttribute = k => k in a.attrs;
  a.setAttribute = (k, v) => { a.attrs[k] = String(v); };
  a.querySelector = sel => (sel === "img" && a.img ? {} : null);
  a.closest = sel => (sel === "a[href]" ? a : null);
  return a;
}
let fails = 0;
function t(name, fn) { try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "\n     " + e.message); } }
const opens = (a) => links.opensNewWindow(a, here);

t("another page on the site opens a new window", () => assert.strictEqual(opens(link("/brigade/")), true));
t("a relative page link opens a new window", () => assert.strictEqual(opens(link("../backlog/")), true));
t("an outside site opens a new window", () => assert.strictEqual(opens(link("https://github.com/Bugs5382")), true));
t("the same page with a different query opens a new window", () => assert.strictEqual(opens(link("/ops/review/?x=2")), true));
t("a # anchor stays on the page", () => assert.strictEqual(opens(link("#s2")), false));
t("this page's own URL with a # anchor stays on the page", () => assert.strictEqual(opens(link("/ops/review/?x=1#s2")), false));
t("a download link keeps its behaviour", () => assert.strictEqual(opens(link("/ops/report.pdf", { download: "" })), false));
t("a link with its own target is left alone", () => assert.strictEqual(opens(link("/ops/", { target: "_self" })), false));
t("a picture link goes to the picture viewer", () => assert.strictEqual(opens(link("img/shot.png", {}, true)), false));
t("a text link to a picture opens a new window", () => assert.strictEqual(opens(link("img/shot.png")), true));
t("mailto and javascript links keep their behaviour", () => {
  assert.strictEqual(opens(link("mailto:a@example.com")), false);
  assert.strictEqual(opens(link("javascript:void(0)")), false);
});
t("an empty href stays on the page", () => assert.strictEqual(opens(link("")), false));

function fakeDoc() {
  const d = { handlers: [], location: here };
  d.addEventListener = (type, fn, capture) => d.handlers.push({ type, fn, capture });
  d.click = target => { const e = { target, defaultPrevented: false }; d.handlers.filter(h => h.type === "click").forEach(h => h.fn(e)); return e; };
  return d;
}
t("hook: a click on a page link sets target and rel", () => {
  const d = fakeDoc(); links.hook(d);
  const a = link("/brigade/");
  const e = d.click({ closest: a.closest });
  assert.strictEqual(a.getAttribute("target"), "_blank");
  assert.strictEqual(a.getAttribute("rel"), "noopener");
  assert.strictEqual(e.defaultPrevented, false);
});
t("hook: an existing rel is kept and gains noopener", () => {
  const d = fakeDoc(); links.hook(d);
  const a = link("/brigade/", { rel: "external" });
  d.click({ closest: a.closest });
  assert.strictEqual(a.getAttribute("rel"), "external noopener");
});
t("hook: a # anchor click changes nothing", () => {
  const d = fakeDoc(); links.hook(d);
  const a = link("#s1");
  d.click({ closest: a.closest });
  assert.strictEqual(a.hasAttribute("target"), false);
});
t("hook: listens in the capture phase and only once per document", () => {
  const d = fakeDoc(); links.hook(d); links.hook(d);
  const clicks = d.handlers.filter(h => h.type === "click");
  assert.strictEqual(clicks.length, 1);
  assert.strictEqual(clicks[0].capture, true);
});
t("hook: a click outside any link is ignored", () => {
  const d = fakeDoc(); links.hook(d);
  d.click({ closest: () => null });
  d.click({});
});

if (fails) { console.log(fails + " failed"); process.exit(1); }

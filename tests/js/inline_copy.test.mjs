// The inline Copy button: inline(text, {copy: true}) in web/src/lib/text.ts. Run by tests/test_inline_copy.py:
// node tests/js/inline_copy.test.mjs web/src/lib/text.ts
import assert from "node:assert";
import { pathToFileURL } from "node:url";

const { inline } = await import(pathToFileURL(process.argv[2]).href);
let fails = 0;
function t(name, fn) { try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "\n     " + e.message); } }
const btn = (v) => `<button type="button" class="copy-inline" data-copy="${v}" aria-label="Copy ${v}">` + ICONS + "</button>";
const ICONS = (inline("`x`", { copy: true }).match(/<button[^>]*>(.*)<\/button>/) ?? [])[1];
t("the button holds the copy icon and a check, both hidden from readers", () => {
  assert.ok(ICONS.includes('<rect width="8" height="4" x="8" y="2"') && ICONS.includes("M20 6 9 17l-5-5"), ICONS);
  assert.strictEqual((ICONS.match(/aria-hidden="true"/g) ?? []).length, 2);
  assert.ok(!/>Copy</.test(ICONS), "icon only, no word");
});

t("without the option the markup is unchanged", () => {
  assert.strictEqual(inline("run `ls -l` or https://a.example/x or [t](https://b.example)"),
    'run <code>ls -l</code> or https://a.example/x or <a href="https://b.example">t</a>');
});
t("a code span is followed by a button that copies its exact text", () => {
  assert.strictEqual(inline("run `ls -l` now", { copy: true }), "run <code>ls -l</code>" + btn("ls -l") + " now");
});
t("a markdown link keeps the link and adds a button for the url", () => {
  assert.strictEqual(inline("[docs](https://a.example/p?x=1&y=2)", { copy: true }),
    '<a href="https://a.example/p?x=1&amp;y=2">docs</a>' + btn("https://a.example/p?x=1&amp;y=2"));
});
t("a bare address gets a button and loses trailing punctuation", () => {
  assert.strictEqual(inline("see https://a.example/p.", { copy: true }),
    'see <span class="copy-src">https://a.example/p</span>' + btn("https://a.example/p") + ".");
});
t("a relative or anchor link gets no button", () => {
  assert.ok(!inline("[x](#top) [y](/a/b)", { copy: true }).includes("copy-inline"));
});
t("the address inside a link is not copied twice", () => {
  assert.strictEqual((inline("[https://a.example](https://a.example)", { copy: true }).match(/copy-inline/g) ?? []).length, 1);
});
t("quotes and markup in the copied text are escaped", () => {
  const h = inline('`a"b<c>*d*`', { copy: true });
  assert.ok(h.includes('data-copy="a&quot;b&lt;c&gt;*d*"'), h);
  assert.ok(!h.includes("<em>"), h);
});
t("bold and italic around a code span still work", () => {
  assert.strictEqual(inline("**a** *b*", { copy: true }), "<strong>a</strong> <em>b</em>");
});
t("a url with asterisks is not mangled by emphasis", () => {
  const h = inline("https://a.example/*x*/*y*", { copy: true });
  assert.ok(h.includes("https://a.example/*x*/*y*") && !h.includes("<em>"), h);
});
t("an empty code span gets no button", () => {
  assert.ok(!inline("``", { copy: true }).includes("copy-inline"));
});
if (fails) process.exit(1);

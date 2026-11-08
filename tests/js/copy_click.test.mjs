// copyText / copyInline in web/src/lib/copy.ts, with a stub browser. Run by tests/test_inline_copy.py:
// node tests/js/copy_click.test.mjs web/src/lib/copy.ts
import assert from "node:assert";
import { pathToFileURL } from "node:url";

const { copyText, copyInline } = await import(pathToFileURL(process.argv[2]).href);
let fails = 0;
async function t(name, fn) { try { await fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "\n     " + e.message); } }

const stub = ({ secure, clip, exec }) => {
  const log = { written: null, selected: false, execd: null, removed: false };
  const ta = { style: {}, select() { log.execd = this.value; }, remove() { log.removed = true; } };
  globalThis.window = { isSecureContext: secure, getSelection: () => ({ removeAllRanges() {}, addRange() { log.selected = true; } }), setTimeout };
  Object.defineProperty(globalThis, "navigator", { value: clip ? { clipboard: { writeText: async v => { log.written = v; } } } : {}, configurable: true });
  globalThis.document = { createElement: () => ta, body: { appendChild() {} }, execCommand: () => exec, createRange: () => ({ selectNodeContents() {} }) };
  return log;
};

await t("a secure context uses the clipboard API", async () => {
  const log = stub({ secure: true, clip: true, exec: false });
  assert.strictEqual(await copyText("abc"), "copied"); assert.strictEqual(log.written, "abc");
});
await t("without a secure context a hidden textarea copies the exact text", async () => {
  const log = stub({ secure: false, clip: false, exec: true });
  assert.strictEqual(await copyText("a b"), "copied"); assert.strictEqual(log.execd, "a b"); assert.ok(log.removed);
});
await t("when nothing can copy, the source text is selected", async () => {
  const log = stub({ secure: false, clip: false, exec: false });
  assert.strictEqual(await copyText("x", {}), "selected"); assert.ok(log.selected);
});
await t("a click on a Copy button shows Copied, then Copy again", async () => {
  stub({ secure: true, clip: true, exec: false });
  const b = { dataset: { copy: "z" }, textContent: "Copy", previousElementSibling: null };
  await copyInline({ target: { closest: () => b } });
  assert.strictEqual(b.textContent, "Copied");
  await new Promise(r => setTimeout(r, 1600));
  assert.strictEqual(b.textContent, "Copy");
});
await t("a click elsewhere does nothing", async () => {
  await copyInline({ target: { closest: () => null } });
});
process.exit(fails ? 1 : 0);

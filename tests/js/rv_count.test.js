// The bar's counting (rvCount in review.js, between the rv-count markers). Run by tests/test_rv_count.py:
// node tests/js/rv_count.test.js template/_site/review.js
const fs = require("fs"), assert = require("assert"), vm = require("vm");
const src = fs.readFileSync(process.argv[2], "utf8");
const m = src.match(/\/\/ rv-count:begin([\s\S]*?)\/\/ rv-count:end/);
assert.ok(m, "rv-count block not found in review.js");
const ctx = { window: {} }; vm.createContext(ctx); vm.runInContext(m[1], ctx);
const rvCount = ctx.window.rvCount;
assert.strictEqual(typeof rvCount, "function");

const ync = id => ({ id, kind: "ync" });
const ch = (id, def = "hold") => ({ id, kind: "choice", def });
const q = id => ({ id, kind: "question" });
const none = { hidden: new Set(), blocked: {} };
let fails = 0;
function t(name, fn) { try { fn(); console.log("ok   " + name); } catch (e) { fails++; console.log("FAIL " + name + "\n     " + e.message); } }

t("ync: partial answers stay dark", () => {
  const r = rvCount([ync("a"), ync("b")], { a: { v: "yes" } }, none);
  assert.strictEqual(r.total, 2); assert.strictEqual(r.answered, 1);
  assert.strictEqual(r.allDone, false); assert.strictEqual(r.approved, false);
  assert.deepStrictEqual(r.openIds, ["b"]);
});
t("ync: Changes without a note is not answered", () => {
  const r = rvCount([ync("a")], { a: { v: "chg", n: " " } }, none);
  assert.strictEqual(r.answered, 0); assert.deepStrictEqual(r.openIds, ["a"]);
});
t("ync: all answered with a No is green, not approved", () => {
  const r = rvCount([ync("a"), ync("b")], { a: { v: "yes" }, b: { v: "no" } }, none);
  assert.strictEqual(r.allDone, true); assert.strictEqual(r.approved, false);
});
t("ync: all Yes is approved", () => {
  const r = rvCount([ync("a"), ync("b")], { a: { v: "yes" }, b: { v: "yes" } }, none);
  assert.strictEqual(r.allDone, true); assert.strictEqual(r.approved, true);
});
t("ync: hidden, blocked and skipped never count", () => {
  const r = rvCount([ync("a"), ync("b"), ync("c"), ync("d")], { a: { v: "yes" }, c: { v: "skip", locked: true } },
    { hidden: new Set(["a"]), blocked: { b: "a" } });
  assert.strictEqual(r.total, 1); assert.strictEqual(r.blocked, 1); assert.strictEqual(r.skipped, 1);
  assert.deepStrictEqual(r.openIds, ["d"]);
});
t("blockers are counted", () => {
  const r = rvCount([ync("a"), ync("b")], { a: { v: "no", n: "x", blocker: true } }, none);
  assert.strictEqual(r.blockers, 1);
});
t("questions never count", () => {
  const r = rvCount([ync("a"), q("q1")], { a: { v: "yes" } }, none);
  assert.strictEqual(r.allDone, true); assert.strictEqual(r.qOpen, 1);
});
t("choices: untouched default is not picked", () => {
  const r = rvCount([ch("b1"), ch("b2")], { b1: { v: "start" } }, none);
  assert.strictEqual(r.total, 2); assert.strictEqual(r.answered, 1);
  assert.strictEqual(r.allDone, false); assert.deepStrictEqual(r.openIds, ["b2"]);
});
t("choices: a comment alone is not a pick", () => {
  const r = rvCount([ch("b1")], { b1: { v: "", n: "later" } }, none);
  assert.strictEqual(r.answered, 0);
});
t("choices: every item picked (even Hold) turns green", () => {
  const r = rvCount([ch("b1"), ch("b2")], { b1: { v: "start" }, b2: { v: "hold" } }, none);
  assert.strictEqual(r.allDone, true); assert.strictEqual(r.approved, false);
  assert.deepStrictEqual(r.openIds, []); assert.strictEqual(r.choiceOnly, true);
});
t("mixed page: green only when ync answered and choices picked", () => {
  const items = [ync("a"), ch("b1")];
  assert.strictEqual(rvCount(items, { a: { v: "yes" } }, none).allDone, false);
  const r = rvCount(items, { a: { v: "yes" }, b1: { v: "hold" } }, none);
  assert.strictEqual(r.allDone, true); assert.strictEqual(r.approved, true);
});
t("empty page is never green", () => {
  assert.strictEqual(rvCount([], {}, none).allDone, false);
});
process.exit(fails ? 1 : 0);

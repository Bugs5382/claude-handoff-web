// @ts-nocheck: carried over from review.js as it stands.
// A Diff / Final switch per block, and one for the whole page when it has several.
export function wireDiffs(): void {
  const blocks = Array.from(document.querySelectorAll(".rvdiff"));
  if (!blocks.length || blocks.every(b => b.dataset.diffWired)) return;
  document.querySelectorAll(".rvdiff-mode").forEach(g => g.remove());
  const KEY = "rvdiff-mode:" + location.pathname;
  let saved = [];
  try { saved = JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch (e) {}
  const save = () => { try { sessionStorage.setItem(KEY, JSON.stringify(blocks.map(b => b.classList.contains("final") ? 1 : 0))); } catch (e) {} };
  const press = (g, v) => g.querySelectorAll("button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.v === v)));
  function group(label, suffix, onPick) {
    const g = document.createElement("div"); g.className = "rvdiff-mode"; g.setAttribute("role", "group"); g.setAttribute("aria-label", label);
    [["diff", "Diff"], ["final", "Final"]].forEach(([v, text]) => {
      const b = document.createElement("button"); b.type = "button"; b.dataset.v = v; b.textContent = text + suffix;
      b.addEventListener("click", () => onPick(v));
      g.appendChild(b);
    });
    return g;
  }
  let all = null;
  function sync() {
    const modes = new Set(blocks.map(b => b.classList.contains("final") ? "final" : "diff"));
    if (all) press(all, modes.size === 1 ? [...modes][0] : "");
    save();
  }
  function set(block, v) { block.classList.toggle("final", v === "final"); press(block.previousElementSibling, v); }
  blocks.forEach((b, i) => {
    b.dataset.diffWired = "1";
    // A sentence removed whole has nothing left to show in Final.
    b.querySelectorAll("p").forEach(p => {
      if (p.querySelector("del") && !Array.from(p.childNodes).some(n => n.nodeName !== "DEL" && n.textContent.trim())) p.classList.add("gone");
    });
    b.before(group("Show the change or the final text", "", v => { set(b, v); sync(); }));
    set(b, saved[i] ? "final" : "diff");
  });
  if (blocks.length > 1) {
    all = group("Show every change or every final text", " for all", v => { blocks.forEach(b => set(b, v)); sync(); });
    all.classList.add("rvdiff-all");
    (document.querySelector("main") || document.body).prepend(all);
  }
  sync();
}

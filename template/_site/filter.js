// Root page project filter: a "Projects" dropdown of checkboxes; the choice is kept in this browser.
(function () {
  const KEY = "site-filter";
  const box = document.getElementById("filter");
  if (!box) return;
  const btn = box.querySelector(".fbtn"), menu = box.querySelector(".fmenu");
  const boxes = Array.from(box.querySelectorAll("input[type=checkbox]"));
  let saved = null;
  try { saved = JSON.parse(localStorage.getItem(KEY)); } catch (e) {}
  if (Array.isArray(saved)) boxes.forEach(b => { b.checked = saved.includes(b.value); });
  const nameOf = b => (b.parentElement.querySelector(".fl") || b.parentElement).textContent.trim();
  function label() {
    const on = boxes.filter(b => b.checked);
    const t = on.length === boxes.length ? "All" : !on.length ? "None" : on.length <= 2 ? on.map(nameOf).join(", ") : on.length + " of " + boxes.length;
    if (btn) btn.firstChild.nodeValue = "Projects: " + t + " ";
  }
  function apply() {
    const on = new Set(boxes.filter(b => b.checked).map(b => b.value));
    let n = 0;
    document.querySelectorAll("#live [data-project]").forEach(el => {
      const show = on.has(el.dataset.project);
      el.style.display = show ? "" : "none";
      if (el.tagName === "SECTION") {
        const k = el.querySelectorAll(".cards > .card").length;
        if (show) n += k;
        const c = box.querySelector('[data-count="' + el.dataset.project + '"]'); if (c && c.textContent !== String(k)) c.textContent = k;
      }
    });
    const c = document.getElementById("now-count"); if (c && c.textContent !== String(n)) c.textContent = n;
    const e = document.getElementById("now-empty"); if (e && e.hidden !== n > 0) e.hidden = n > 0;
    label();
  }
  function save() { localStorage.setItem(KEY, JSON.stringify(boxes.filter(b => b.checked).map(b => b.value))); apply(); }
  function show(on, focusBtn) {
    if (!menu || !btn) return;
    menu.hidden = !on; btn.setAttribute("aria-expanded", String(on));
    if (on) { const f = menu.querySelector("input"); if (f) f.focus(); } else if (focusBtn) btn.focus();
  }
  boxes.forEach(b => b.addEventListener("change", save));
  box.querySelector("[data-all]").addEventListener("click", () => { boxes.forEach(b => b.checked = true); save(); });
  box.querySelector("[data-none]").addEventListener("click", () => { boxes.forEach(b => b.checked = false); save(); });
  if (btn) btn.addEventListener("click", () => show(menu.hidden));
  document.addEventListener("click", e => { if (menu && !menu.hidden && !box.contains(e.target)) show(false); });
  box.addEventListener("keydown", e => { if (e.key === "Escape" && menu && !menu.hidden) { e.preventDefault(); show(false, true); } });
  box.addEventListener("focusout", e => { if (menu && !menu.hidden && e.relatedTarget && !box.contains(e.relatedTarget)) show(false); });
  const live = document.getElementById("live");
  // Re-apply only when live.js swaps the cards in; ignore our own count update (that looped before).
  let busy = false;
  if (live) new MutationObserver(() => { if (busy) return; busy = true; try { apply(); } finally { setTimeout(() => { busy = false; }, 0); } }).observe(live, { childList: true });
  apply();
})();

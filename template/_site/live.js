// Live pages: poll this page's own URL every 10 s (paused while the tab is hidden).
//   Index mode (default; pages with #live): swap the card lists in place and light up New/Updated.
//   Page mode (<script data-mode="page">, review pages): soft-reload when the HTML changes, but
//   only when nobody is typing and nothing was clicked for 5 s; scroll position is kept.
// Index cards carry data-key, data-sig, data-mtime and data-first (epoch seconds); the "New" and
// "Updated" chips are worked out here so they age without a rebuild.
(function () {
  const me = document.currentScript || document.querySelector('script[src*="/_site/live.js"]');
  const mode = (me && me.getAttribute("data-mode")) || (document.getElementById("live") ? "index" : "page");
  const POLL = 10000, IDLE = 5000, DAY = 86400, FLASH = 30000;
  const path = location.pathname;
  let lastAct = 0, baseline = null, busy = false;

  function toast(text) {
    const t = document.createElement("div"); t.className = "site-toast"; t.textContent = text; t.setAttribute("role", "status");
    document.body.appendChild(t); requestAnimationFrame(() => t.classList.add("show"));
    setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 400); }, 2600);
  }
  async function fetchSelf() {
    const r = await fetch(location.href.split("#")[0], { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return r.text();
  }

  // ---------- index mode ----------
  const visitKey = "site-visit:" + path;
  const prevVisit = +localStorage.getItem(visitKey) || 0;
  const loadedAt = Date.now() / 1000;
  const since = prevVisit || (loadedAt - DAY);
  const marks = {};  // key -> { chip, until }

  function chip(cls, text, lit) {
    const c = document.createElement("span"); c.className = "chip " + cls + (lit ? " lit" : ""); c.textContent = text; c.setAttribute("data-live", "1"); return c;
  }
  function decorate() {
    const now = Date.now() / 1000;
    for (const card of document.querySelectorAll("#live [data-key]")) {
      const box = card.querySelector(".chips"); if (!box) continue;
      box.querySelectorAll("[data-live]").forEach(x => x.remove());
      const first = +card.dataset.first || 0, mt = +card.dataset.mtime || 0, mk = marks[card.dataset.key];
      const live = mk && mk.until > Date.now() ? mk.chip : "";
      const isNew = live === "new" || (first && now - first < DAY);
      const isUpd = live === "updated" || (mt > since && mt > first + 60);
      if (isUpd) box.prepend(chip("c-updated", "Updated", live === "updated"));
      if (isNew) box.prepend(chip("c-new", "New", live === "new"));
      card.classList.toggle("flash", !!live);
    }
  }
  function keyMap(root) {
    const m = {};
    for (const c of root.querySelectorAll("[data-key]")) {
      const sect = (c.closest("[data-sect]") || { dataset: {} }).dataset.sect || "";
      (m[c.dataset.key] = m[c.dataset.key] || []).push(sect + "|" + c.dataset.sig);
    }
    return m;
  }
  async function pollIndex() {
    const html = await fetchSelf();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const fresh = doc.getElementById("live"), cur = document.getElementById("live");
    if (!fresh || !cur) return;
    const sig = fresh.innerHTML;
    if (baseline === null) { baseline = sig; return; }
    if (sig === baseline) return;
    baseline = sig;
    const before = keyMap(cur), after = keyMap(fresh);
    const open = new Set(Array.from(cur.querySelectorAll("details[data-sect]")).filter(d => d.open).map(d => d.dataset.sect));
    cur.innerHTML = fresh.innerHTML;
    cur.querySelectorAll("details[data-sect]").forEach(d => { if (open.has(d.dataset.sect)) d.open = true; });
    for (const [k, v] of Object.entries(after)) {
      const was = before[k];
      if (!was) marks[k] = { chip: "new", until: Date.now() + FLASH };
      else if (was.join() !== v.join()) marks[k] = { chip: "updated", until: Date.now() + FLASH };
    }
    decorate();
    setTimeout(decorate, FLASH + 200);
    toast("Updated just now");
  }

  // ---------- page mode ----------
  const SCROLL = "site-live-scroll:" + path;
  function typing() {
    const a = document.activeElement;
    if (!a) return false;
    if (a.tagName === "TEXTAREA" || a.isContentEditable) return true;
    return a.tagName === "INPUT" && !/^(radio|checkbox|button|submit|reset)$/i.test(a.type);
  }
  async function pollPage() {
    const html = await fetchSelf();
    if (baseline === null) { baseline = html; return; }
    if (html === baseline) return;
    if (typing() || Date.now() - lastAct < IDLE) return;  // try again on the next poll
    if (window.siteReview && window.siteReview.unsaved && window.siteReview.unsaved()) return;  // answers not on the box yet
    sessionStorage.setItem(SCROLL, JSON.stringify({ x: scrollX, y: scrollY, t: Date.now() }));
    location.reload();
  }
  if (mode === "page") {
    for (const ev of ["input", "change", "keydown", "pointerdown", "focusin"]) document.addEventListener(ev, () => { lastAct = Date.now(); }, true);
    const saved = JSON.parse(sessionStorage.getItem(SCROLL) || "null");
    if (saved && Date.now() - saved.t < 60000) {
      sessionStorage.removeItem(SCROLL);
      const go = () => { scrollTo(saved.x, saved.y); toast("Updated just now"); };
      if (document.readyState === "complete") go(); else addEventListener("load", go);
    }
  } else {
    decorate();
    localStorage.setItem(visitKey, String(Math.floor(loadedAt)));
  }

  // Stale buttons (index cards and unified review groups): confirm, ask the server to delete the page,
  // then refresh straight away so the card or group disappears.
  document.addEventListener("click", async e => {
    const b = e.target.closest && e.target.closest(".stale-btn");
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    const folder = b.dataset.staleFolder, page = b.dataset.stalePage, title = b.dataset.staleTitle || page;
    if (!confirm("Stale: delete \"" + title + "\" (" + folder + "/" + page + ") for good?\nIt is removed from the site and marked done. This can't be undone.")) return;
    b.disabled = true; b.textContent = "Removing...";
    try {
      const r = await fetch("/_stale", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder, page }), cache: "no-store" });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.error || ("HTTP " + r.status));
      toast("Removed as stale: " + title);
      const grp = b.closest("details.grp, .card"); if (grp) grp.style.display = "none";
      if (mode === "page") {
        const reload = () => { if (window.siteReview && window.siteReview.unsaved && window.siteReview.unsaved()) return setTimeout(reload, 1000); sessionStorage.setItem(SCROLL, JSON.stringify({ x: scrollX, y: scrollY, t: Date.now() })); location.reload(); };
        setTimeout(reload, 800);
      } else await tick();
    } catch (err) {
      b.disabled = false; b.textContent = "Stale: remove this page";
      alert("Couldn't mark it stale: " + err.message);
    }
  }, true);

  let timer = null;
  async function tick() {
    if (busy || document.hidden) return;
    busy = true;
    try { await (mode === "page" ? pollPage() : pollIndex()); } catch (e) { /* server busy or offline: next poll */ }
    busy = false;
  }
  function start() { if (!timer) { tick(); timer = setInterval(tick, POLL); } }
  function stop() { clearInterval(timer); timer = null; }
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });
  if (!document.hidden) start();
  window.siteLive = { mode, tick };
})();

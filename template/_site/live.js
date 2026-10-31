// Live pages: poll this page's own URL every 10 s (paused while the tab is hidden).
//   Index mode (default; pages with #live): swap the card lists in place and light up New/Updated.
//   Page mode (<script data-mode="page">, review pages): soft-reload when the HTML changes, but
//   only when nobody is typing and nothing was clicked for 5 s; scroll position is kept.
//   File mode (<script data-mode="file">, pages drawn from a page file): no polling, render.js redraws
//   those itself; only the picture pop-out and the theme.
// Index cards carry data-key, data-sig, data-mtime and data-first (epoch seconds); the "New" and
// "Updated" chips are worked out here so they age without a rebuild.
// Theme toggle: index and plain pages that don't load /_site/theme.js in <head> get it here.
if (!window.siteTheme) { const t = document.createElement("script"); t.src = "/_site/theme.js?v=20"; document.head.appendChild(t); }

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
  // "2 min ago" on index cards (the full time stays in the title).
  function ago(ts, now) {
    const s = Math.max(0, now - ts), m = Math.round(s / 60), h = Math.round(s / 3600), d = Math.round(s / 86400);
    return s < 60 ? "just now" : m < 60 ? m + " min ago" : h < 24 ? h + " h ago" : d + (d === 1 ? " day ago" : " days ago");
  }
  function decorate() {
    const now = Date.now() / 1000;
    for (const el of document.querySelectorAll("#live .ago[data-ts]")) { const t = ago(+el.dataset.ts, now); if (el.textContent !== t) el.textContent = t; }
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
  } else if (mode === "index") {
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

  // Links: a link to another page opens in a new window, so the page under review stays put. The
  // target is set as the click happens, which covers cards and threads that are redrawn later.
  // Same-page # anchors, picture links (the viewer below), downloads, non-web links and links that
  // set their own target keep their behaviour.
  // new-window:begin
  window.siteLinks = (function () {
    const PICTURE = /\.(png|jpe?g|gif|webp|svg)$/i;
    function opensNewWindow(a, here) {
      if (!a || a.hasAttribute("download") || a.hasAttribute("target")) return false;
      const raw = (a.getAttribute("href") || "").trim();
      if (!raw || raw[0] === "#") return false;
      let u;
      try { u = new URL(a.href, here.href); } catch (err) { return false; }
      if (u.protocol !== "http:" && u.protocol !== "https:") return false;
      if (u.hash && u.origin === here.origin && u.pathname === here.pathname && u.search === here.search) return false;
      if (a.querySelector("img") && PICTURE.test(u.pathname)) return false;
      return true;
    }
    function hook(doc) {
      if (!doc || doc.siteLinks) return;
      doc.siteLinks = true;
      doc.addEventListener("click", e => {
        const a = e.target && e.target.closest && e.target.closest("a[href]");
        if (!opensNewWindow(a, doc.location || location)) return;
        a.setAttribute("target", "_blank");
        const rel = (a.getAttribute("rel") || "").split(/\s+/).filter(Boolean);
        if (!rel.includes("noopener")) a.setAttribute("rel", rel.concat("noopener").join(" "));
      }, true);
    }
    return { opensNewWindow, hook };
  })();
  // new-window:end
  window.siteLinks.hook(document);

  // Pictures: a plain click on a link that wraps an <img> and points at an image file shows it in
  // one reused popup window ("picture"); the next picture swaps into that same window. Middle and
  // modified clicks, and a blocked popup, fall through to the plain link. The unified review page
  // renders details in srcdoc frames, so each frame's document gets the same handler.
  const PIC = /\.(png|jpe?g|gif|webp|svg)$/i;
  const PIC_PAGE = '<!doctype html><html lang="en"' + (document.documentElement.getAttribute("data-theme") ? ' data-theme="' + document.documentElement.getAttribute("data-theme") + '"' : "") +
    '><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<title>Picture</title><link rel="stylesheet" href="' + location.origin + '/_site/site.css?v=26"></head><body class="pic-win"><div class="stage"><img id="pic" alt=""></div>' +
    '<div class="bar"><span id="cap"></span><a id="full" target="_blank" rel="noopener">Full size</a></div></body></html>';
  function pictureLink(e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return null;
    const a = e.target && e.target.closest && e.target.closest("a[href]");
    if (!a || a.hasAttribute("download") || !a.querySelector("img")) return null;
    try { return PIC.test(new URL(a.href).pathname) ? a : null; } catch (err) { return null; }
  }
  function showPicture(e) {
    const a = pictureLink(e);
    if (!a) return;
    const w = window.open("", "picture", "width=1000,height=760");
    if (!w) return;
    e.preventDefault();
    const name = decodeURIComponent(new URL(a.href).pathname.split("/").pop());
    const cap = (a.querySelector("img").getAttribute("alt") || "").trim() || name;
    try {
      const d = w.document;
      if (!d.getElementById("pic")) { d.open(); d.write(PIC_PAGE); d.close(); }
      const img = d.getElementById("pic");
      img.src = a.href; img.alt = cap;
      d.getElementById("cap").textContent = cap;
      d.getElementById("full").href = a.href;
      d.title = cap;
    } catch (err) {
      w.location.href = a.href;  // the window was navigated somewhere we can't write to
    }
    w.focus();
  }
  function hookFrame(f) {
    try {
      const d = f.contentDocument;
      if (d && !d.sitePictures) { d.sitePictures = true; d.addEventListener("click", showPicture); }
      window.siteLinks.hook(d);
    } catch (err) { /* cross-origin frame: its links behave as usual */ }
  }
  document.addEventListener("click", showPicture);
  document.querySelectorAll("iframe").forEach(hookFrame);
  document.addEventListener("load", e => { if (e.target && e.target.tagName === "IFRAME") hookFrame(e.target); }, true);

  let timer = null;
  async function tick() {
    if (busy || document.hidden) return;
    busy = true;
    if (mode === "file") return;
    try { await (mode === "page" ? pollPage() : pollIndex()); } catch (e) { /* server busy or offline: next poll */ }
    busy = false;
  }
  function start() { if (!timer) { tick(); timer = setInterval(tick, POLL); } }
  if (mode !== "page") setInterval(() => { if (!document.hidden) decorate(); }, 60000);
  function stop() { clearInterval(timer); timer = null; }
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else start(); });
  if (!document.hidden) start();
  window.siteLive = { mode, tick };
})();

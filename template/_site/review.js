// Shared review controls. Every <h2> section (and every [data-review-question] element) gets
// Yes / No / Changes and a notes box. Answers are stored only on the box, through the site server:
// GET/PUT /_save/<page-key>.json (see SAVE-API.md), as { id: { v: "yes"|"no"|"chg", n: "note" } }.
// The page key is KEY_PREFIX + page, lower-cased with anything outside [a-z0-9._-] turned
// into "-". Saves are debounced (500 ms) and retried until the box answers; the bar shows
// "Saved hh:mm" or "Not saved, retrying". Answers an older version kept in this browser's
// localStorage (same key) are uploaded once, read back, and only then removed from the browser.
// Body attributes:
//   data-review-page      storage page id (default: the path)
//   data-review-approved  "s1,s3": answered Yes in a pasted result; hidden, count as Yes
//   data-review-reopen    "s4=reason|s11=reason": brings an answered item back, with a reason
//   data-review-stale     "a.html|b/": pages marked Stale recently; listed as "STALE: <page>" in Copy results
//   data-review-reset     "v2:s1,s2" clears those answers (and reopened ones) once per version;
//                         "tag@v2:a.s1|tag2@v1:b.s2" does the same per tag. Cleared answers are
//                         kept under state._prev, never dropped.
// The page also polls itself (/_site/live.js) and soft-reloads when it changes.
// "How to test": an item's test steps open in their own pop-out window (named "howto", reused so it
// stays where he put it), never inline with the answers. Sources, per item:
//   <template data-howto>...steps...</template>   inside the item (or its h2 section)
//   <div class="howto">...</div>                   converted to a template automatically
//   .item .how                                     checklist hint lines, converted the same way
// The window shows the item id, its title and the build under test (body data-build).
// Unified pages: size each detail iframe to its content, again whenever its group or toggle opens.
window.rvFit = function (f) { try { const h = f.contentDocument.documentElement.scrollHeight; if (h) f.style.height = (h + 8) + "px"; } catch (e) {} };
document.addEventListener("toggle", e => { if (e.target.open) e.target.querySelectorAll("iframe.shot").forEach(window.rvFit); }, true);

(function () {
  // Pages that render their own items (and their own pop-out) opt out.
  if (document.body.getAttribute("data-review-controls") === "off") return;
  const V = "10";
  function itemOf(el) {
    const box = el.closest("[data-review-question], .item");
    if (box) {
      const id = box.getAttribute("data-review-question") || box.id.replace(/^item-/, "");
      const t = box.querySelector(".q, .ih") || box;
      return { id, title: box.getAttribute("data-title") || textOf(t), at: t };
    }
    let n = el; while (n && n.tagName !== "H2") n = n.previousElementSibling || (n.parentElement !== document.body ? n.parentElement : null);
    if (!n) return null;
    const i = Array.from(document.querySelectorAll("h2")).indexOf(n);
    return { id: "s" + (i + 1), title: textOf(n), at: n };
  }
  function textOf(el) { const c = el.cloneNode(true); c.querySelectorAll(".chip, .howto-btn, template").forEach(x => x.remove()); return c.textContent.trim().replace(/\s+/g, " "); }
  function open(tpl, it) {
    const w = window.open("about:blank", "howto", "width=520,height=720");
    if (!w) { alert("Allow pop-ups for this site to see the test steps."); return; }
    const build = document.body.getAttribute("data-build");
    const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    const d = w.document; d.open();
    d.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<title>How to test: ' + esc(it.id) + '</title><link rel="stylesheet" href="' + location.origin + '/_site/site.css?v=' + V + '"></head>' +
      '<body class="site page howto-win"><p class="muted">How to test &middot; <code>' + esc(it.id) + '</code>' + (build ? ' &middot; Build under test: <code>' + esc(build) + '</code>' : '') + '</p>' +
      '<h1>' + esc(it.title) + '</h1><div class="howto-body"></div><p class="muted">Answer on the main page.</p></body></html>');
    d.close();
    d.querySelector(".howto-body").appendChild(d.importNode(tpl.content, true));
    d.querySelectorAll(".howto-body pre, .howto-body code.cmd").forEach(blk => {
      const b = d.createElement("button"); b.type = "button"; b.className = "copy-cmd"; b.textContent = "Copy";
      b.addEventListener("click", async () => {
        const t = blk.textContent.trim();
        try { await w.navigator.clipboard.writeText(t); } catch (e) { const x = d.createElement("textarea"); x.value = t; d.body.appendChild(x); x.select(); d.execCommand("copy"); x.remove(); }
        b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500);
      });
      blk.insertAdjacentElement("afterend", b);
    });
    w.focus();
  }
  function wire(tpl) {
    if (tpl.dataset.howtoWired) return; tpl.dataset.howtoWired = "1";
    const it = itemOf(tpl); if (!it) return;
    const b = document.createElement("button"); b.type = "button"; b.className = "howto-btn"; b.textContent = "How to test";
    b.addEventListener("click", e => { e.preventDefault(); e.stopPropagation(); open(tpl, it); });
    it.at.append(" ", b);
  }
  function scan() {
    document.querySelectorAll(".howto:not(template), .item .how").forEach(el => {
      if (!el.textContent.trim() && !el.children.length) { el.remove(); return; }
      const t = document.createElement("template"); t.setAttribute("data-howto", "");
      while (el.firstChild) t.content.appendChild(el.firstChild);
      el.replaceWith(t);
    });
    document.querySelectorAll("template[data-howto]").forEach(wire);
  }
  scan();
  new MutationObserver(() => scan()).observe(document.body, { childList: true, subtree: true });
  window.siteHowto = { scan };
})();

(function () {
  const body = document.body;
  if (body.getAttribute("data-review-controls") === "off") { loadLive(); return; }
  const page = body.getAttribute("data-review-page") || location.pathname.replace(/\/index\.html$/, "/");
  // Set once per install (install.sh writes both from site.json: key_prefix, blocker_to).
  const KEY_PREFIX = "review:";
  const BLOCKER_TO = "the operator session";
  const KEY = KEY_PREFIX + page;

  // ---------- box storage (/_save/<page-key>.json, see SAVE-API.md) ----------
  function pageKey(k) {
    let s = k.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|-+$/g, "");
    if (s.length > 120) { let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0; s = s.slice(0, 111) + "-" + h.toString(36); }
    return s || "page";
  }
  const SAVE_URL = "/_save/" + pageKey(KEY) + ".json";
  const TZ = body.getAttribute("data-tz") || undefined;
  const hhmm = d => d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ });
  const store = { seq: 0, sent: 0, timer: null, busy: false, fails: 0, loadPending: false, migrate: false, touched: new Set(), msg: "", bad: false, lastMod: null };
  async function getBox() {
    const r = await fetch(SAVE_URL, { cache: "no-store" });
    if (r.status === 404) return null;
    if (!r.ok) throw new Error("GET " + r.status);
    const lm = r.headers.get("Last-Modified"); store.lastMod = lm ? new Date(lm) : null;
    return await r.json();
  }
  async function putBox(obj) {
    const r = await fetch(SAVE_URL, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj), cache: "no-store" });
    if (r.status !== 204) throw new Error("PUT " + r.status);
  }
  function readLocal() {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    try { const o = JSON.parse(raw); return o && typeof o === "object" && Object.keys(o).length ? o : null; } catch (e) { return null; }
  }
  // One-time move of answers saved in this browser: upload, read back, and only then drop the local copy.
  async function migrateLocal(local) {
    try {
      await putBox(local);
      const back = await getBox();
      if (back && JSON.stringify(back) === JSON.stringify(local)) { localStorage.removeItem(KEY); store.migrate = false; return true; }
    } catch (e) { /* box busy: retried after the next good save */ }
    store.migrate = true; return false;
  }

  function mergeLocal(box, local) {
    const empty = o => !o || typeof o !== "object" || (!o.v && !(o.n || "").trim() && !o.locked && !o.blocker);
    for (const [k, v] of Object.entries(local)) {
      if (k === "_prev") {
        box._prev = box._prev || {};
        for (const [id, arr] of Object.entries(v || {})) box._prev[id] = (box._prev[id] || []).concat(arr);
      } else if (!(k in box) || (!k.startsWith("_") && !k.startsWith("import:") && empty(box[k]) && !empty(v))) box[k] = v;
    }
    return box;
  }

  (async function boot() {
    let state = {};
    try {
      const b = await getBox();
      const local = readLocal();
      state = b && typeof b === "object" ? b : {};
      // Another browser may have created the box copy first: fill in what only this browser has.
      if (local) { mergeLocal(state, local); await migrateLocal(state); }
    } catch (e) {
      // Box unreachable: work from memory (and any local copy), never PUT over the box blindly.
      state = readLocal() || {}; store.loadPending = true; store.migrate = !!readLocal();
    }
    run(state);
  })();

  function run(state) {
  function setStatus(text, bad) { store.msg = text; store.bad = !!bad; const el = document.querySelector(".rvbar .svst"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); } }
  function persist(id) {
    if (id) store.touched.add(id);
    store.seq++; clearTimeout(store.timer); store.timer = setTimeout(flush, 500);
  }
  async function flush() {
    if (store.busy) { clearTimeout(store.timer); store.timer = setTimeout(flush, 300); return; }
    if (store.sent === store.seq && !store.loadPending) return;
    store.busy = true; const seq = store.seq; let repaint = false;
    try {
      if (store.loadPending) {
        const b = await getBox();
        if (b && typeof b === "object") {
          const merged = b;
          for (const id of store.touched) { if (id in state) merged[id] = state[id]; else delete merged[id]; }
          repaint = Object.keys(b).some(k => !store.touched.has(k) && JSON.stringify(b[k]) !== JSON.stringify(state[k]));
          for (const k of Object.keys(state)) delete state[k];
          Object.assign(state, merged);
        }
        store.loadPending = false;
      }
      await putBox(state);
      store.sent = seq; store.fails = 0;
      setStatus("Saved " + hhmm(new Date()));
      if (store.migrate) { const back = await getBox(); if (back && JSON.stringify(back) === JSON.stringify(state)) { localStorage.removeItem(KEY); store.migrate = false; } }
      if (repaint) softReload();
    } catch (e) {
      store.fails++;
      setStatus("Not saved, retrying", true);
      clearTimeout(store.timer); store.timer = setTimeout(flush, Math.min(15000, 1000 * Math.pow(2, store.fails)));
    } finally { store.busy = false; }
    if (store.sent !== store.seq && !store.timer) store.timer = setTimeout(flush, 500);
  }
  function unsaved() { return store.sent !== store.seq || store.loadPending; }
  async function flushNow() { clearTimeout(store.timer); store.timer = null; while (store.busy) await new Promise(r => setTimeout(r, 50)); await flush(); return !unsaved(); }
  function softReload() {
    const a = document.activeElement;
    if (a && (a.tagName === "TEXTAREA" || a.isContentEditable)) { setTimeout(softReload, 2000); return; }
    location.reload();
  }
  addEventListener("beforeunload", e => {
    if (!unsaved()) return;
    try { fetch(SAVE_URL, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state), keepalive: true }); } catch (x) {}
    e.preventDefault(); e.returnValue = "";
  });

  const reset = body.getAttribute("data-review-reset");
  const reopen = {};
  for (const part of (body.getAttribute("data-review-reopen") || "").split("|")) {
    const i = part.indexOf("="); if (i > 0) reopen[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  const blocked = {};
  for (const part of (body.getAttribute("data-review-blocked") || "").split("|")) {
    const i = part.indexOf("="); if (i > 0) blocked[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  function archive(id) {
    if (!(id in state)) return;
    state._prev = state._prev || {};
    (state._prev[id] = state._prev[id] || []).push(state[id]);
    delete state[id];
    store.touched.add(id); store.touched.add("_prev");
  }
  if (reset) {
    let changed = false;
    for (const spec of reset.split("|")) {
      const c = spec.indexOf(":"); const head = c < 0 ? spec : spec.slice(0, c); const ids = c < 0 ? "" : spec.slice(c + 1);
      const at = head.indexOf("@"); const tag = at < 0 ? "" : head.slice(0, at).trim(); const ver = (at < 0 ? head : head.slice(at + 1)).trim();
      const seen = tag ? (state._resets || {})[tag] : state._reset;
      if (seen === ver) continue;
      const extra = Object.keys(reopen).filter(id => !tag || id.startsWith(tag + "."));
      for (const id of ids.split(",").concat(extra)) if (id.trim()) archive(id.trim());
      if (tag) { state._resets = state._resets || {}; state._resets[tag] = ver; store.touched.add("_resets"); } else { state._reset = ver; store.touched.add("_reset"); }
      changed = true;
    }
    if (changed) persist();
  }

  if (!document.querySelector('link[href*="/_site/site.css"]')) {
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "/_site/site.css?v=10"; document.head.appendChild(l);
  }

  // data-review-skip="on" (test checklists): adds Skipped; a skipped item is locked.
  const SKIP = body.getAttribute("data-review-skip") === "on";
  const OPTS = ["yes:Yes", "no:No", "chg:Changes"].concat(SKIP ? ["skip:Skipped"] : []);
  const items = [];
  // data-review-h2="off": only [data-review-question] elements are items (converted pages).
  if (body.getAttribute("data-review-h2") !== "off") Array.from(document.querySelectorAll("h2")).forEach((h, i) => {
    const id = "s" + (i + 1);
    let anchor = h; let n = h.nextElementSibling;
    const nodes = [h];
    while (n && n.tagName !== "H2" && !n.hasAttribute("data-review-question") && n.tagName !== "SCRIPT") { anchor = n; nodes.push(n); n = n.nextElementSibling; }
    const hc = h.cloneNode(true); hc.querySelectorAll(".howto-btn").forEach(x => x.remove());
    items.push({ id, title: hc.textContent.trim(), after: anchor, nodes });
  });
  document.querySelectorAll("[data-review-question]").forEach(el => {
    items.push({ id: el.getAttribute("data-review-question"), title: el.getAttribute("data-title") || el.textContent.trim(), at: el, nodes: [el] });
  });
  // data-review-import="oldKey|prefix": one-time import of answers an older checklist saved in this
  // browser as { id: { status: "pass"|"fail"|"skip", notes } }. The old key is left untouched.
  const imp = body.getAttribute("data-review-import");
  if (imp) {
    const [ok, pre] = imp.split("|"); const tag = "import:" + ok;
    if (!state[tag]) {
      let old = {}; try { old = JSON.parse(localStorage.getItem(ok) || "{}") || {}; } catch (e) {}
      const map = { pass: "yes", fail: "no", skip: "skip" };
      for (const [id, o] of Object.entries(old)) {
        const nid = (pre || "") + id;
        if (state[nid] || !o || !(o.status || o.notes)) continue;
        const v = map[o.status] || (o.notes ? "chg" : "");
        state[nid] = { v, n: o.notes || "" }; if (v === "skip") state[nid].locked = true;
        store.touched.add(nid);
      }
      state[tag] = 1; persist(tag);
    }
  }
  const approved = (body.getAttribute("data-review-approved") || "").split(",").map(x => x.trim()).filter(x => x && !reopen[x]);
  for (const id of approved) state[id] = { v: "yes", n: (state[id] || {}).n || "" };
  const hidden = new Set(items.filter(it => !reopen[it.id] && (approved.includes(it.id) || (reset && (state[it.id] || {}).v === "yes"))).map(it => it.id));

  for (const it of items) {
    const box = document.createElement("div"); box.className = "rv"; box.id = "rv-" + it.id;
    const s = state[it.id] || {};
    const st = document.createElement("span"); st.className = "st";
    if (blocked[it.id]) { st.classList.add("blk"); st.textContent = "Blocked by " + blocked[it.id]; }
    else if (reopen[it.id]) { st.classList.add("reo"); st.textContent = "Reopened: " + reopen[it.id]; } else st.textContent = s.locked ? "Skipped (locked)" : "Open";
    box.appendChild(st);
    const row = document.createElement("div");
    row.innerHTML = '<span class="ask">Your answer:</span><span class="opts">' +
      OPTS.map(o => { const [v, l] = o.split(":"); return '<label><input type="radio" name="rv-' + it.id + '" value="' + v + '"' + (s.v === v ? " checked" : "") + "> " + l + "</label>"; }).join("") +
      '</span><span class="need">Please say what to change.</span>';
    box.appendChild(row);
    const ta = document.createElement("textarea"); ta.placeholder = "Notes (required for Changes)"; ta.value = s.n || "";
    box.appendChild(ta);
    box.addEventListener("change", e => {
      if (e.target.value === "skip" && !(state[it.id] || {}).locked) {
        if (!confirm("Skip this item? Once skipped it's locked and can't be changed.")) { const p = (state[it.id] || {}).v; box.querySelectorAll("input[type=radio]").forEach(r => r.checked = r.value === p); return; }
        state[it.id] = { v: "skip", n: ta.value, locked: true }; lock(it); persist(it.id); paint(); return;
      }
      save(it.id);
    });
    ta.addEventListener("input", () => save(it.id));
    const bk = document.createElement("button"); bk.type = "button"; bk.className = "blocker-btn";
    bk.textContent = "Blocker: copy now"; bk.title = "Something stops you testing or using it: copy this one item and paste it to " + BLOCKER_TO + " straight away";
    bk.addEventListener("click", async () => {
      const cur = state[it.id] || {};
      let n = ta.value.trim();
      if (!n) { n = (prompt("What is blocking you? (one line)") || "").trim(); if (!n) return; ta.value = n; }
      state[it.id] = Object.assign({}, cur, { n, blocker: true }); persist(it.id); paint();
      const build = body.getAttribute("data-build");
      const out = "BLOCKER: " + document.title + " (" + page + (build ? ", build " + build : "") + ")\n- [" + it.id + "] " + it.title + "\n    Note: " + n.replace(/\n/g, " ") + "\n";
      try { await navigator.clipboard.writeText(out); } catch (e) { const t = document.createElement("textarea"); t.value = out; body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
      alert("Blocker copied. Paste it to " + BLOCKER_TO + " now.");
    });
    box.appendChild(bk);
    // Unified pages keep bulky content in .rv-details: the answer controls go above it.
    const det = it.at && it.at.querySelector(":scope > .rv-details");
    if (det) det.before(box); else if (it.at) it.at.appendChild(box); else it.after.insertAdjacentElement("afterend", box);
    it.box = box;
    if (s.locked || blocked[it.id]) lock(it);
    if (blocked[it.id]) box.classList.add("blocked");
    if (hidden.has(it.id)) { for (const el of [box].concat(it.nodes)) el.style.setProperty("display", "none", "important"); }
  }
  if (hidden.size) {
    const note = document.createElement("div"); note.className = "rvdone";
    note.textContent = hidden.size + " approved and hidden. They stay in Copy results.";
    const first = document.querySelector("h2, [data-review-question]");
    if (first) first.insertAdjacentElement("beforebegin", note); else body.appendChild(note);
  }

  // Lean bar: count + saved status, Previous/Next, the open ids behind a toggle, and a More menu.
  const bar = document.createElement("div"); bar.className = "rvbar";
  bar.innerHTML = '<span class="cnt"></span><span class="svst" role="status" aria-live="polite"></span>' +
    '<button class="prev" type="button" title="Previous open item (p)">Previous</button><button class="next" type="button" title="Next open item (n)">Next</button>' +
    '<button class="ids" type="button" aria-expanded="false" title="Show the open item ids">Open ids</button>' +
    '<span class="more"><button class="more-btn" type="button" aria-haspopup="menu" aria-expanded="false">More</button>' +
    '<span class="menu" role="menu" hidden><button class="copy" type="button" role="menuitem">Copy results</button><button class="clear" type="button" role="menuitem">Clear my answers</button></span></span>' +
    '<span class="jump" hidden></span>';
  body.appendChild(bar);
  const menu = bar.querySelector(".menu"), moreBtn = bar.querySelector(".more-btn"), jumpEl = bar.querySelector(".jump"), idsBtn = bar.querySelector(".ids");
  function showMenu(on) { menu.hidden = !on; moreBtn.setAttribute("aria-expanded", String(on)); }
  function showIds(on) { jumpEl.hidden = !on; idsBtn.setAttribute("aria-expanded", String(on)); }
  moreBtn.addEventListener("click", e => { e.stopPropagation(); showIds(false); showMenu(menu.hidden); });
  idsBtn.addEventListener("click", e => { e.stopPropagation(); showMenu(false); showIds(jumpEl.hidden); });
  document.addEventListener("click", e => { if (!bar.contains(e.target)) { showMenu(false); showIds(false); } });
  document.addEventListener("keydown", e => { if (e.key === "Escape") { showMenu(false); showIds(false); } });
  if (store.msg) setStatus(store.msg, store.bad);
  else if (store.loadPending) setStatus("Not saved, retrying", true);
  else if (store.lastMod) setStatus("Saved " + hhmm(store.lastMod));
  if (store.loadPending) persist();

  function lock(it) {
    it.box.querySelectorAll("input, textarea").forEach(x => x.disabled = true);
    it.box.classList.add("locked"); it.box.querySelector(".st").textContent = "Skipped (locked)";
  }
  function save(id) {
    for (const it of items) {
      if (hidden.has(it.id) || (state[it.id] || {}).locked) continue;
      const v = (it.box.querySelector("input:checked") || {}).value || "";
      const n = it.box.querySelector("textarea").value;
      state[it.id] = Object.assign({ v, n }, (state[it.id] || {}).blocker ? { blocker: true } : {});
    }
    persist(id); paint();
  }
  function paint() {
    let done = 0;
    for (const it of items) {
      const s = state[it.id] || {};
      it.box.classList.remove("yes", "no", "chg", "skip", "empty", "blocker");
      if (s.v) it.box.classList.add(s.v);
      if (s.blocker) it.box.classList.add("blocker");
      if (s.v === "chg" && !(s.n || "").trim()) it.box.classList.add("empty");
      if (!hidden.has(it.id) && !s.locked && s.v && !(s.v === "chg" && !(s.n || "").trim())) done++;
    }
    const open = items.filter(it => !hidden.has(it.id) && !(state[it.id] || {}).locked && !blocked[it.id]).length;
    const nb = items.filter(it => !hidden.has(it.id) && blocked[it.id]).length;
    const yesAll = items.filter(it => !hidden.has(it.id) && !blocked[it.id] && !(state[it.id] || {}).locked).every(it => (state[it.id] || {}).v === "yes");
    bar.classList.toggle("all-done", open > 0 && done === open);
    bar.classList.toggle("approved", open > 0 && done === open && yesAll);
    if (open > 0 && done === open) { bar.querySelector(".cnt").textContent = (yesAll ? "APPROVED: " : "") + "All " + open + " done" + (nb ? " · " + nb + " blocked" : "") + (hidden.size ? " · " + hidden.size + " approved and hidden" : ""); }
    else bar.querySelector(".cnt").textContent = done + " of " + open + " open items answered" + (nb ? " · " + nb + " blocked" : "") + (hidden.size ? " · " + hidden.size + " approved and hidden" : "");
    jumpEl.innerHTML = "";
    const list = openList();
    for (const it of list) { const a = document.createElement("a"); a.href = "#rv-" + it.id; a.className = "chip c-review"; a.textContent = it.id; a.addEventListener("click", e => { e.preventDefault(); showIds(false); go(it); }); jumpEl.appendChild(a); }
    idsBtn.textContent = "Open ids (" + list.length + ")"; idsBtn.disabled = !list.length;
    if (!list.length) showIds(false);
  }
  function openList() {
    return items.filter(it => { const s = state[it.id] || {}; return !hidden.has(it.id) && !s.locked && !blocked[it.id] && (!s.v || (s.v === "chg" && !(s.n || "").trim())); });
  }
  function go(it) {
    const el = it.nodes[0] || it.box;
    for (let d = el.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) d.open = true; el.scrollIntoView({ behavior: "smooth", block: "start" });
    const f = it.box.querySelector("input:not(:disabled)"); if (f) setTimeout(() => f.focus({ preventScroll: true }), 400);
  }
  function step(dir) {
    const list = openList(); if (!list.length) return;
    const y = window.scrollY + 80;
    const pos = list.map(it => (it.nodes[0] || it.box).getBoundingClientRect().top + window.scrollY);
    let i = dir > 0 ? pos.findIndex(t => t > y + 5) : pos.map(t => t < y - 5).lastIndexOf(true);
    if (i < 0) i = dir > 0 ? 0 : list.length - 1;
    go(list[i]);
  }
  bar.querySelector(".next").addEventListener("click", () => step(1));
  bar.querySelector(".prev").addEventListener("click", () => step(-1));
  document.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || "")) return;
    if (e.key === "n") step(1); else if (e.key === "p") step(-1);
  });
  paint();

  const stalePages = (body.getAttribute("data-review-stale") || "").split("|").map(x => x.trim()).filter(Boolean);
  const label = { yes: "YES", no: "NO", chg: "CHANGES", skip: "SKIPPED (locked)" };
  const session = (location.pathname.split("/")[1] || "the").toUpperCase();
  function results() {
    let out = "Review: " + document.title + " (" + page + ")\n";
    for (const it of items) {
      const s = state[it.id] || {};
      out += "- [" + it.id + "] " + (blocked[it.id] ? "BLOCKED by " + blocked[it.id] + ", " : "") + (s.blocker ? "BLOCKER, " : "") + (label[s.v] || "NOT ANSWERED") + ": " + it.title + (s.n ? "\n    Note: " + s.n.replace(/\n/g, " ") : "") + "\n";
    }
    for (const p of stalePages) out += "STALE: " + p + "\n";
    const counted = items.filter(it => !(state[it.id] || {}).locked);
    const yes = counted.filter(it => (state[it.id] || {}).v === "yes").length;
    out += "\n" + (yes === counted.length ? "APPROVED: every item is Yes." : "Not approved yet: " + yes + " of " + counted.length + " are Yes.") + "\n";
    // Unified pages prefix ids with their source page ("built.s2"); report each page's approval too.
    const groups = {};
    for (const it of items) { const g = it.id.includes(".") ? it.id.split(".")[0] : ""; if (!g) continue;
      (groups[g] = groups[g] || { n: 0, yes: 0 }).n++; if ((state[it.id] || {}).v === "yes") groups[g].yes++; }
    for (const [g, c] of Object.entries(groups)) out += "  " + g + ": " + (c.yes === c.n ? "APPROVED" : c.yes + " of " + c.n + " Yes") + "\n";
    return out;
  }
  bar.querySelector(".copy").addEventListener("click", async () => {
    showMenu(false);
    const out = results();
    try { await navigator.clipboard.writeText(out); } catch (e) { const t = document.createElement("textarea"); t.value = out; body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
    alert("Copied. Paste it into the " + session + " session.");
  });
  bar.querySelector(".clear").addEventListener("click", async () => {
    showMenu(false);
    if (!confirm("Clear your answers on this page? Approved and Skipped (locked) items stay.")) return;
    for (const it of items) if (!hidden.has(it.id) && !(state[it.id] || {}).locked) { delete state[it.id]; store.touched.add(it.id); }
    persist();
    if (await flushNow()) location.reload();
    else { paint(); alert("Cleared here, but the box can't be reached yet. It keeps retrying; don't close the page until it says Saved."); }
  });
  window.siteReview = { results, unsaved, saveUrl: SAVE_URL };
  const target = location.hash && document.getElementById(location.hash.slice(1));
  if (target) for (let d = target.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) d.open = true;

  loadLive();
  }

  function loadLive() {
    if (document.querySelector('script[src*="/_site/live.js"]')) return;
    const sc = document.createElement("script"); sc.src = "/_site/live.js?v=10"; sc.setAttribute("data-mode", "page"); body.appendChild(sc);
  }
})();

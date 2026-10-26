// Shared review controls. Every <h2> section (and every [data-review-question] element) gets
// Yes / No / Changes and a notes box. Answers are stored only on the box, through the site server:
// GET/PUT /_save/<page-key>.json (see SAVE-API.md), as { id: { v: "yes"|"no"|"chg", n: "note" } }.
// The page key is KEY_PREFIX + page, lower-cased with anything outside [a-z0-9._-] turned
// into "-". Saves are debounced (500 ms) and retried until the box answers; the bar shows
// "Saved hh:mm" or "Not saved · retrying". Answers an older version kept in this browser's
// localStorage (same key) are uploaded once, read back, and only then removed from the browser.
// Body attributes:
//   data-review-page      storage page id (default: the path)
//   data-review-approved  "s1,s3": answered Yes in a pasted result; hidden, count as Yes
//   data-review-reopen    "s4=reason|s11=reason": brings an answered item back, with a reason
//   data-review-stale     "a.html|b/": pages marked Stale recently; listed as "STALE: <page>" in Copy results
//   data-review-reset     "v2:s1,s2" clears those answers (and reopened ones) once per version;
//                         "tag@v2:a.s1|tag2@v1:b.s2" does the same per tag. Cleared answers are
//                         kept under state._prev, never dropped.
//   data-review-options   "start:Start,hold:Hold": the page's own answer choices (value:label, in order)
//                         instead of Yes / No / Changes. Also allowed on one <h2> or [data-review-question]
//                         item, which then overrides the page (the unified page sets it per item).
//   data-review-default   "hold": the choice an item shows and counts as until the owner picks one.
//                         It is never written to the save file: { v: "" } (or no entry) means "the
//                         default", so changing the page's default later moves every item nobody picked.
//                         Choice items are never open, approved, hidden or blocking; the bar and Copy
//                         results count them per choice ("2 start · 12 hold").
// Round history: a round is this page's run under one data-build value or data-review-reset
// version. The server archives a round's answers (serve.py) the moment either one changes, or on
// More, "Save round now". Past rounds show at GET /_history/<page-key>/ (see SAVE-API.md): a
// collapsed "History (n rounds)" block at the bottom of the page, each round its own collapsed
// item with a one-line summary and the same Copy results text, never expanded automatically and
// never ahead of the page's own content.
// The page also polls itself (/_site/live.js) and soft-reloads when it changes.
// Page files: on a page drawn by render.js (window.sitePage), the items come from the renderer, answers are
// saved through sitePage (PUT /_page/<page>/answers) instead of /_save/, History comes from the page's own
// rounds, Blocker sends the item to the page's route ("Blocker: send now", unless the route only copies), the
// bar gains "Send to <agent>" and a delivery line, and render.js redraws the page in place through
// siteReview.unmount() and siteReviewMount() instead of a reload.
// "How to test": an item's test steps open in their own pop-out window (named "howto", reused so it
// stays where he put it), never inline with the answers. Sources, per item:
//   <template data-howto>...steps...</template>   inside the item (or its h2 section)
//   <div class="howto">...</div>                   converted to a template automatically
//   .item .how                                     checklist hint lines, converted the same way
// The window shows the item id, its title and the build under test (body data-build).
// Unified pages: size each detail iframe to its content, again whenever its group or toggle opens.
window.rvFit = function (f) { try { const h = f.contentDocument.documentElement.scrollHeight; if (h) f.style.height = (h + 8) + "px"; } catch (e) {} };
document.addEventListener("toggle", e => { if (e.target.open) e.target.querySelectorAll("iframe.shot").forEach(window.rvFit); }, true);

// rv-count:begin
// What the bottom bar counts. items: [{ id, kind: "ync" | "choice" | "question" }]; state: the saved
// answers; o: { hidden: Set of approved-and-hidden ids, blocked: { id: blocker } }.
// A Yes / No / Changes item is answered once it has an answer (Changes needs a note); approved and
// hidden, skipped (locked) and blocked items never count. A choice item is answered once the owner
// picked something: the untouched default is not a pick, and neither is a comment alone. Questions
// never count. allDone (the green bar) needs every counted item answered; approved also needs every
// Yes / No / Changes item to be Yes.
window.rvCount = function (items, state, o) {
  const hidden = o.hidden, blocked = o.blocked, S = id => state[id] || {};
  const ync = items.filter(it => it.kind === "ync"), choice = items.filter(it => it.kind === "choice");
  const counted = ync.filter(it => !hidden.has(it.id) && !S(it.id).locked && !blocked[it.id]);
  const unanswered = it => !S(it.id).v || (S(it.id).v === "chg" && !(S(it.id).n || "").trim());
  const cCounted = choice.filter(it => !blocked[it.id]);
  const unpicked = it => !S(it.id).v;
  const open = counted.filter(unanswered), cOpen = cCounted.filter(unpicked);
  const total = counted.length + cCounted.length, answered = total - open.length - cOpen.length;
  const hiddenN = ync.filter(it => hidden.has(it.id)).length;
  const blockedN = ync.concat(choice).filter(it => !hidden.has(it.id) && blocked[it.id]).length;
  const yesAll = counted.every(it => S(it.id).v === "yes");
  // Everything already approved and hidden: nothing left to answer, and all of it is Yes.
  const allHidden = total === 0 && hiddenN > 0 && !blockedN;
  const allDone = (total > 0 && answered === total) || allHidden;
  return {
    total, answered, allDone, approved: allDone && (counted.length > 0 || allHidden) && yesAll,
    yncTotal: counted.length, choiceTotal: cCounted.length, picked: cCounted.length - cOpen.length,
    openIds: items.filter(it => open.includes(it) || cOpen.includes(it)).map(it => it.id),
    hidden: hiddenN, blocked: blockedN,
    skipped: ync.filter(it => !hidden.has(it.id) && S(it.id).locked).length,
    blockers: ync.filter(it => !hidden.has(it.id) && S(it.id).blocker).length,
    qOpen: items.filter(it => it.kind === "question" && !(S(it.id).a || "").trim()).length,
    choiceOnly: choice.length > 0 && ync.length === 0
  };
};
// rv-count:end

(function () {
  // Pages that render their own items (and their own pop-out) opt out.
  if (document.body.getAttribute("data-review-controls") === "off") return;
  const V = "20";
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
    const th = document.documentElement.getAttribute("data-theme");
    d.write('<!doctype html><html lang="en"' + (th ? ' data-theme="' + esc(th) + '"' : "") + '><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
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
    const b = document.createElement("button"); b.type = "button"; b.className = "howto-btn"; b.textContent = "How to test \u2197";
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

// Theme toggle (Auto / Light / Dark): pages that don't load /_site/theme.js in <head> get it here.
if (!window.siteTheme) { const t = document.createElement("script"); t.src = "/_site/theme.js?v=20"; document.head.appendChild(t); }

(function () {
  const body = document.body;
  const PF = window.sitePage || null;
  if (body.getAttribute("data-review-controls") === "off") { loadLive(); return; }
  const page = body.getAttribute("data-review-page") || location.pathname.replace(/\/index\.html$/, "/");
  // Set once per install (install.sh writes both from site.json: key_prefix, blocker_to).
  const KEY_PREFIX = "review:";
  let BLOCKER_TO = "the operator session";
  const KEY = KEY_PREFIX + page;

  // ---------- box storage (/_save/<page-key>.json, see SAVE-API.md) ----------
  function pageKey(k) {
    let s = k.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|-+$/g, "");
    if (s.length > 120) { let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0; s = s.slice(0, 111) + "-" + h.toString(36); }
    return s || "page";
  }
  const SAVE_URL = "/_save/" + pageKey(KEY) + ".json";
  const HIST_NAME = pageKey(KEY);
  const HIST_URL = "/_history/" + HIST_NAME + "/";
  const TZ = body.getAttribute("data-tz") || undefined;
  const hhmm = d => d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: TZ });
  const freshStore = () => ({ seq: 0, sent: 0, timer: null, busy: false, fails: 0, loadPending: false, migrate: false, touched: new Set(), msg: "", bad: false, lastMod: null });
  const store = freshStore();
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

  if (PF) {
    window.siteReviewMount = () => { Object.assign(store, freshStore(), { lastMod: PF.lastSaved() }); run(PF.state()); };
    window.siteReviewMount();
  } else (async function boot() {
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
  // Listeners on window and document go through on(), so unmount() can take them off before a redraw.
  const offs = [];
  const on = (t, ev, fn, o) => { t.addEventListener(ev, fn, o); offs.push(() => t.removeEventListener(ev, fn, o)); };
  function setStatus(text, bad) { store.msg = text; store.bad = !!bad; const el = document.querySelector(".rvbar .svst"); if (el) { el.textContent = text; el.classList.toggle("bad", !!bad); el.closest(".rvbar").classList.toggle("save-bad", !!bad); } }
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
      await (PF ? PF.save(state) : putBox(state));
      store.sent = seq; store.fails = 0;
      setStatus("Saved " + hhmm(new Date()));
      if (store.migrate) { const back = await getBox(); if (back && JSON.stringify(back) === JSON.stringify(state)) { localStorage.removeItem(KEY); store.migrate = false; } }
      if (repaint) softReload();
    } catch (e) {
      store.fails++;
      setStatus("Not saved \u00b7 retrying", true);
      clearTimeout(store.timer); store.timer = setTimeout(flush, Math.min(15000, 1000 * Math.pow(2, store.fails)));
    } finally { store.busy = false; }
    if (store.sent !== store.seq && !store.timer) store.timer = setTimeout(flush, 500);
  }
  function unsaved() { return store.sent !== store.seq || store.loadPending; }
  async function flushNow() { clearTimeout(store.timer); store.timer = null; while (store.busy) await new Promise(r => setTimeout(r, 50)); await flush(); return !unsaved(); }
  function softReload() {
    const a = document.activeElement;
    if (a && (a.tagName === "TEXTAREA" || a.isContentEditable)) { setTimeout(softReload, 2000); return; }
    if (PF) PF.redraw(); else location.reload();
  }
  on(window, "beforeunload", e => {
    if (!unsaved()) return;
    try {
      if (PF) PF.saveKeepalive(state);
      else fetch(SAVE_URL, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state), keepalive: true });
    } catch (x) {}
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
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "/_site/site.css?v=23"; document.head.appendChild(l);
  }

  // data-review-skip="on" (test checklists): adds Skipped; a skipped item is locked.
  const SKIP = body.getAttribute("data-review-skip") === "on";
  const OPTS = ["yes:Yes", "no:No", "chg:Changes"].concat(SKIP ? ["skip:Skipped"] : []);
  function parseOpts(spec) {
    return (spec || "").split(",").map(p => { const i = p.indexOf(":"); return i > 0 ? [p.slice(0, i).trim(), p.slice(i + 1).trim()] : null; }).filter(o => o && o[0] && o[1]);
  }
  const PAGE_OPTS = parseOpts(body.getAttribute("data-review-options"));
  const PAGE_DEF = body.getAttribute("data-review-default") || "";
  function choicesOf(el) {
    const own = el && el.hasAttribute("data-review-options") ? parseOpts(el.getAttribute("data-review-options")) : [];
    const opts = own.length ? own : PAGE_OPTS;
    if (!opts.length) return null;
    const d = (el && el.getAttribute("data-review-default")) || PAGE_DEF;
    return { opts, def: opts.some(o => o[0] === d) ? d : "" };
  }
  const items = [];
  // A page file: the renderer hands over its items (each one a section card it drew).
  if (PF) PF.items.forEach(x => items.push({ id: x.id, title: x.title, at: x.el, nodes: [x.el], type: x.type, suggested: x.suggested, ch: choicesOf(x.el) }));
  // data-review-h2="off": only [data-review-question] elements are items (converted pages).
  else if (body.getAttribute("data-review-h2") !== "off") Array.from(document.querySelectorAll("h2")).forEach((h, i) => {
    const id = "s" + (i + 1);
    let anchor = h; let n = h.nextElementSibling;
    const nodes = [h];
    while (n && n.tagName !== "H2" && !n.hasAttribute("data-review-question") && n.tagName !== "SCRIPT") { anchor = n; nodes.push(n); n = n.nextElementSibling; }
    const hc = h.cloneNode(true); hc.querySelectorAll(".howto-btn").forEach(x => x.remove());
    items.push({ id, title: hc.textContent.trim(), after: anchor, nodes, type: h.getAttribute("data-review-type") || "", suggested: h.getAttribute("data-suggested") || "", ch: choicesOf(h) });
  });
  if (!PF) document.querySelectorAll("[data-review-question]").forEach(el => {
    items.push({ id: el.getAttribute("data-review-question"), title: el.getAttribute("data-title") || el.textContent.trim(), at: el, nodes: [el], type: el.getAttribute("data-review-type") || "", suggested: el.getAttribute("data-suggested") || "", ch: choicesOf(el) });
  });
  const isQ = it => it.type === "question";
  for (const it of items) if (isQ(it)) it.ch = null;
  const isC = it => !!it.ch;
  const choiceIds = new Set(items.filter(isC).map(it => it.id));
  const valOf = it => (state[it.id] || {}).v || it.ch.def;
  const labelOf = (it, v) => (it.ch.opts.find(o => o[0] === v) || [v, v])[1];
  function choiceStatus(it) {
    const v = (state[it.id] || {}).v;
    return v ? labelOf(it, v) : it.ch.def ? labelOf(it, it.ch.def) + " (default)" : "Not chosen";
  }
  // "2 start · 12 hold": every choice the items offer, in order, with how many items sit on it.
  function tally(list) {
    const c = new Map();
    for (const it of list) {
      for (const o of it.ch.opts) if (!c.has(o[1].toLowerCase())) c.set(o[1].toLowerCase(), 0);
      const v = valOf(it); if (v) { const k = labelOf(it, v).toLowerCase(); c.set(k, (c.get(k) || 0) + 1); }
    }
    return Array.from(c).map(([k, n]) => n + " " + k).join(" · ");
  }
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
  const approved = (body.getAttribute("data-review-approved") || "").split(",").map(x => x.trim()).filter(x => x && !reopen[x] && !choiceIds.has(x));
  for (const id of approved) state[id] = { v: "yes", n: (state[id] || {}).n || "" };
  const hidden = new Set(items.filter(it => !isC(it) && !reopen[it.id] && (approved.includes(it.id) || (reset && (state[it.id] || {}).v === "yes"))).map(it => it.id));

  function saveQuestion(id, answer) {
    state[id] = Object.assign({}, state[id] || {}, { a: answer });
    persist(id); paint();
  }
  function grow(ta) { ta.style.height = "auto"; ta.style.height = (ta.scrollHeight + 2) + "px"; }

  // Items: a [data-review-question] section on a plain page becomes the card itself (.rvcard), with
  // its id and status pill on top; <h2> items and unified-page items get the controls in their own card.
  // Answers are a segmented group of real buttons; pressing the chosen one again clears it.
  const ANS = { yes: "Yes", no: "No", chg: "Changes", skip: "Skipped (locked)" };
  // On a page file, Blocker and Send go to the page's route unless it only copies.
  const SENDS = !!PF && PF.route.mode !== "copy";
  if (PF) BLOCKER_TO = PF.route.to;
  const UNIFIED = body.classList.contains("unified");
  function place(it, box) {
    const det = it.at && it.at.querySelector(":scope > .rv-details");
    if (det) det.before(box); else if (it.at) it.at.appendChild(box); else it.after.insertAdjacentElement("afterend", box);
    it.box = box;
    if (it.at && !UNIFIED && it.at.tagName !== "H2") {
      it.card = it.at; it.card.classList.add("rvcard"); box.classList.add("in-card");
      const head = box.querySelector(".rvhead"); if (head) it.card.prepend(head);
    }
  }
  function headEl(it) {
    const h = document.createElement("div"); h.className = "rvhead";
    h.innerHTML = '<span class="rid"></span><span class="sp"></span><span class="st2" data-pill="2"></span><span class="st" data-pill="1" role="status"></span>';
    h.querySelector(".rid").textContent = it.id;
    return h;
  }
  function segEl(it, opts) {
    const g = document.createElement("div"); g.className = "seg"; g.setAttribute("role", "group"); g.setAttribute("aria-label", "Answer for " + it.id);
    opts.forEach(([v, l], i) => {
      const b = document.createElement("button"); b.type = "button"; b.dataset.v = v; b.dataset.label = l; b.textContent = l;
      b.setAttribute("aria-pressed", "false");
      if (it.ch) b.classList.add(i === 0 ? "first" : "other");
      g.appendChild(b);
    });
    return g;
  }
  function pressed(it) { const b = it.box.querySelector(".seg button[aria-pressed=true]"); return b ? b.dataset.v : ""; }
  function setPressed(it, v) { it.box.querySelectorAll(".seg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.v === v))); }

  for (const it of items) {
    const box = document.createElement("div"); box.className = "rv"; box.id = "rv-" + it.id;
    const s = state[it.id] || {};
    const head = headEl(it); box.appendChild(head);
    const st = head.querySelector("[data-pill='1']");
    if (isQ(it)) {
      box.classList.add("question");
      if (blocked[it.id]) { st.classList.add("blk"); st.textContent = "Blocked by " + blocked[it.id]; }
      else if (reopen[it.id]) { st.classList.add("reo"); st.textContent = "Reopened: " + reopen[it.id]; } else st.textContent = "Question";
      const qrow = document.createElement("div"); qrow.className = "qrow";
      qrow.innerHTML = '<span class="ask">Your answer:</span>' + (it.suggested ? '<button type="button" class="suggest-btn">Use suggestion</button>' : "");
      box.appendChild(qrow);
      const qa = document.createElement("textarea"); qa.className = "qans"; qa.placeholder = "Type your answer"; qa.value = s.a || "";
      box.appendChild(qa);
      qa.addEventListener("input", () => { grow(qa); saveQuestion(it.id, qa.value); });
      if (it.suggested) qrow.querySelector(".suggest-btn").addEventListener("click", () => { qa.value = it.suggested; grow(qa); saveQuestion(it.id, qa.value); qa.focus(); });
      place(it, box);
      if (blocked[it.id]) { box.classList.add("blocked"); if (it.card) it.card.classList.add("is-blocked"); }
      requestAnimationFrame(() => grow(qa));
      continue;
    }
    if (isC(it)) {
      // The page's own choices: no Blocker button, notes optional, and only what the owner picks is saved.
      box.classList.add("choice");
      const row = document.createElement("div"); row.className = "rvrow";
      row.innerHTML = '<span class="ask">Your answer:</span>';
      row.appendChild(segEl(it, it.ch.opts));
      box.appendChild(row);
      const nl = document.createElement("label"); nl.className = "notel";
      nl.innerHTML = "<span>Comments (optional)</span>";
      const cta = document.createElement("textarea"); cta.rows = 2; cta.value = s.n || "";
      nl.appendChild(cta); box.appendChild(nl);
      row.addEventListener("click", e => {
        const b = e.target.closest(".seg button"); if (!b || b.disabled) return;
        const v = b.dataset.v === ((state[it.id] || {}).v || "") ? "" : b.dataset.v;
        state[it.id] = Object.assign({}, state[it.id] || {}, { v, n: cta.value });
        persist(it.id); paint();
      });
      cta.addEventListener("input", () => {
        state[it.id] = Object.assign({ v: "" }, state[it.id] || {}, { n: cta.value });
        persist(it.id); paint();
      });
      place(it, box);
      if (it.card) it.card.classList.add("is-choice");
      if (blocked[it.id]) { box.classList.add("blocked"); if (it.card) it.card.classList.add("is-blocked"); box.querySelectorAll("button, textarea").forEach(x => x.disabled = true); }
      continue;
    }
    const row = document.createElement("div"); row.className = "rvrow";
    row.innerHTML = '<span class="ask">Your answer:</span>';
    row.appendChild(segEl(it, OPTS.map(o => o.split(":"))));
    const addNote = document.createElement("button"); addNote.type = "button"; addNote.className = "add-note"; addNote.textContent = "Add a note";
    const sp = document.createElement("span"); sp.className = "sp";
    const bk = document.createElement("button"); bk.type = "button"; bk.className = "blocker-btn";
    bk.textContent = SENDS ? "Blocker: send now" : "Blocker: copy now";
    bk.title = SENDS ? "Something stops you testing or using it: send this one item to " + BLOCKER_TO + " straight away"
      : "Something stops you testing or using it: copy this one item and paste it to " + BLOCKER_TO + " straight away";
    row.append(addNote, sp, bk);
    box.appendChild(row);
    const nl = document.createElement("label"); nl.className = "notel";
    nl.innerHTML = '<span><span class="nlt">Note</span> <span class="need">Please say what to change.</span></span>';
    const ta = document.createElement("textarea"); ta.rows = 3; ta.placeholder = "Notes (required for Changes)"; ta.value = s.n || "";
    nl.appendChild(ta); box.appendChild(nl);
    addNote.addEventListener("click", () => { it.noteOpen = true; paint(); ta.focus(); });
    row.querySelector(".seg").addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b || b.disabled) return;
      const prev = (state[it.id] || {}).v || "";
      const v = b.dataset.v === prev ? "" : b.dataset.v;
      if (v === "skip" && !(state[it.id] || {}).locked) {
        if (!confirm("Skip this item? Once skipped it's locked and can't be changed.")) return;
        setPressed(it, "skip");
        state[it.id] = { v: "skip", n: ta.value, locked: true }; lock(it); persist(it.id); paint(); return;
      }
      setPressed(it, v);
      save(it.id);
      if (v === "chg" && !ta.value.trim()) ta.focus();
    });
    ta.addEventListener("input", () => save(it.id));
    bk.addEventListener("click", async () => {
      const cur = state[it.id] || {};
      let n = ta.value.trim();
      if (!n) { n = (prompt("What is blocking you? (one line)") || "").trim(); if (!n) return; ta.value = n; }
      state[it.id] = Object.assign({}, cur, { n, blocker: true }); persist(it.id); paint();
      const build = body.getAttribute("data-build");
      const out = "BLOCKER: " + document.title + " (" + page + (build ? ", build " + build : "") + ")\n- [" + it.id + "] " + it.title + "\n    Note: " + n.replace(/\n/g, " ") + "\n";
      if (SENDS) {
        try {
          if (!(await flushNow())) throw new Error("the answers aren't saved yet");
          const sent = await PF.send("blocker", [it.id], out);
          setDelivery("Sent " + hhmm(new Date()) + (sent.listening ? "" : " · " + sent.to + " isn't listening; Copy results instead"));
          alert("Blocker sent to " + sent.to + "." + (sent.listening ? "" : " " + sent.to + " isn't listening right now, so paste it to them as well."));
          if (!sent.listening) await copyText(out);
        } catch (err) {
          await copyText(out);
          alert("Couldn't send the blocker (" + err.message + "), so it's copied. Paste it to " + BLOCKER_TO + " now.");
        }
        return;
      }
      await copyText(out);
      alert("Blocker copied. Paste it to " + BLOCKER_TO + " now.");
    });
    place(it, box);
    if (s.locked || blocked[it.id]) lock(it);
    if (blocked[it.id]) { box.classList.add("blocked"); if (it.card) it.card.classList.add("is-blocked"); }
    if (hidden.has(it.id)) { for (const el of [box].concat(it.nodes)) el.style.setProperty("display", "none", "important"); }
  }
  if (hidden.size) {
    const note = document.createElement("div"); note.className = "rvdone";
    note.textContent = hidden.size + " approved and hidden. They stay in Copy results.";
    const first = document.querySelector("h2, [data-review-question]");
    if (first) first.insertAdjacentElement("beforebegin", note); else body.appendChild(note);
  }
  // Header: a way back to the folder on pages that don't carry one.
  const top = document.querySelector("header.top .wrap"), folder = location.pathname.split("/")[1] || "";
  const FOLDER_URL = "/" + folder + "/";
  const FOLDER_PAGES = (folder.length <= 3 ? folder.toUpperCase() : folder.slice(0, 1).toUpperCase() + folder.slice(1)) + " pages";
  if (top && folder && !top.querySelector(".crumb") && !UNIFIED) {
    const a = document.createElement("a"); a.className = "crumb"; a.href = FOLDER_URL;
    a.textContent = "\u2190 " + FOLDER_PAGES;
    top.prepend(a);
  }
  // Finished pages point back to the folder index: a toast with the link when the page turns green,
  // and after Copy results on a finished page, a return to the folder after 1.5 s unless he moves,
  // scrolls or types (never while typing, and only once every answer is on the box).
  function actToast(text, linkText) {
    document.querySelectorAll(".site-toast.act").forEach(x => x.remove());
    const t = document.createElement("div"); t.className = "site-toast act"; t.setAttribute("role", "status");
    const sp = document.createElement("span"); sp.textContent = text; t.appendChild(sp);
    if (linkText && folder) { const a = document.createElement("a"); a.href = FOLDER_URL; a.textContent = linkText; t.appendChild(a); }
    body.appendChild(t); requestAnimationFrame(() => t.classList.add("show"));
    setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 400); }, 4000);
    return t;
  }
  function typingNow() {
    const a = document.activeElement;
    return !!a && (a.tagName === "TEXTAREA" || a.isContentEditable || (a.tagName === "INPUT" && !/^(radio|checkbox|button|submit|reset)$/i.test(a.type)));
  }
  let backTimer = null;
  function returnSoon() {
    if (!folder || backTimer) return;
    let x0 = null, y0 = null;
    const stay = () => { clearTimeout(backTimer); backTimer = null; off(); actToast("Staying on this page.", "\u2190 Back to " + FOLDER_PAGES); };
    const move = e => { if (x0 === null) { x0 = e.clientX; y0 = e.clientY; return; } if (Math.abs(e.clientX - x0) + Math.abs(e.clientY - y0) > 12) stay(); };
    const evs = [["keydown", stay], ["wheel", stay], ["pointerdown", stay], ["touchstart", stay], ["pointermove", move]];
    const off = () => evs.forEach(([n, f]) => removeEventListener(n, f, true));
    evs.forEach(([n, f]) => addEventListener(n, f, true));
    actToast("Done. Back to " + FOLDER_PAGES + " in a moment \u00b7 move or type to stay", "Go now");
    backTimer = setTimeout(async () => {
      off(); backTimer = null;
      if (typingNow()) return;
      if (!(await flushNow())) { actToast("Not saved yet, so staying here.", ""); return; }
      location.href = FOLDER_URL;
    }, 1500);
  }

  // Bottom bar: Previous, Next, the Open IDs picker (opens upward, with a filter), the status, the
  // Saved time and More. Colour states: dark while items are open, green when every one is answered,
  // green "APPROVED" when all are Yes, a red ring for a marked blocker, amber when a save fails.
  const bar = document.createElement("div"); bar.className = "rvbar"; bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Review progress");
  bar.innerHTML = '<div class="rvbar-in">' +
    '<div class="rvpop rvids" role="dialog" aria-label="Open IDs" hidden><label class="rvids-l"><span class="rvids-h"></span>' +
    '<input type="search" autocomplete="off" spellcheck="false" placeholder="Type an ID or words from the title"></label>' +
    '<div class="rvids-list" role="listbox"></div>' +
    '<div class="rvids-keys"><span>↑↓ move</span><span>Enter jump</span><span>Esc close</span><span>n / p next, previous</span></div></div>' +
    '<div class="rvpop menu" role="menu" hidden><button class="all-yes" type="button" role="menuitem">Mark unanswered Yes</button>' +
    '<button class="all-no" type="button" role="menuitem">Mark unanswered No</button>' +
    '<button class="copy" type="button" role="menuitem">Copy results</button>' +
    '<button class="copy-blockers" type="button" role="menuitem">Copy blockers only</button>' +
    '<button class="history" type="button" role="menuitem" disabled>History</button>' +
    '<button class="round-close" type="button" role="menuitem">Save round now</button>' +
    '<button class="clear" type="button" role="menuitem">Clear my answers</button></div>' +
    '<button class="prev" type="button" title="Previous open item (p)" aria-label="Previous open item">← <span class="lg">Previous</span><span class="sm">Prev</span></button>' +
    '<button class="next" type="button" title="Next open item (n)" aria-label="Next open item">Next →</button>' +
    '<button class="ids" type="button" aria-haspopup="dialog" aria-expanded="false"><span class="ids-l"></span> <span class="mono ids-n"></span> ▴</button>' +
    '<span class="stat"><span class="dot" aria-hidden="true"></span>' +
    '<svg class="tick" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9.5l4 4 8-9" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"></path></svg>' +
    '<span class="bkr" hidden></span><span class="cnt" role="status" aria-live="polite"></span></span>' +
    '<span class="svst" aria-live="polite"></span>' +
    '<a class="back" hidden></a>' +
    (SENDS ? '<button class="send-btn" type="button"></button><span class="dlv" aria-live="polite"></span>' : "") +
    '<span class="more"><button class="more-btn" type="button" aria-haspopup="menu" aria-expanded="false">More ▾</button></span>' +
    '</div>';
  body.appendChild(bar);
  function setDelivery(text) { const el = bar.querySelector(".dlv"); if (el) el.textContent = text; }
  const sendBtn = bar.querySelector(".send-btn");
  if (sendBtn) {
    sendBtn.textContent = "Send to " + PF.route.to;
    setDelivery(PF.delivery());
  }
  const menu = bar.querySelector(".menu"), moreBtn = bar.querySelector(".more-btn"), idsBtn = bar.querySelector(".ids");
  const picker = bar.querySelector(".rvids"), pickIn = picker.querySelector("input"), pickList = picker.querySelector(".rvids-list"), pickHead = picker.querySelector(".rvids-h");
  const choicePage = items.some(isC) && !items.some(it => !isQ(it) && !isC(it));
  const MAX_ROWS = 200;
  let pickActive = 0, pickShown = [];
  function showMenu(on) { menu.hidden = !on; moreBtn.setAttribute("aria-expanded", String(on)); }
  function showIds(on) {
    picker.hidden = !on; idsBtn.setAttribute("aria-expanded", String(on));
    if (on) {
      picker.style.left = Math.max(0, Math.min(idsBtn.offsetLeft, bar.querySelector(".rvbar-in").clientWidth - picker.offsetWidth)) + "px";
      if (matchMedia("(max-width: 480px)").matches) picker.style.left = "";
      pickIn.value = ""; pickActive = 0; renderPicker(); pickIn.focus();
    }
  }
  moreBtn.addEventListener("click", e => { e.stopPropagation(); showIds(false); showMenu(menu.hidden); });
  idsBtn.addEventListener("click", e => { e.stopPropagation(); showMenu(false); showIds(picker.hidden); });
  on(document, "click", e => { if (!bar.contains(e.target)) { showMenu(false); showIds(false); } });
  on(document, "keydown", e => {
    if (e.key !== "Escape") return;
    if (!picker.hidden) { showIds(false); idsBtn.focus(); } else if (!menu.hidden) { showMenu(false); moreBtn.focus(); }
  });
  function renderPicker() {
    const all = jumpList();
    const words = pickIn.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const hit = words.length ? all.filter(it => { const t = (it.id + " " + it.title).toLowerCase(); return words.every(w => t.includes(w)); }) : all;
    pickShown = hit.slice(0, MAX_ROWS);
    if (pickActive >= pickShown.length) pickActive = Math.max(0, pickShown.length - 1);
    const noun = choicePage ? "not picked" : "open";
    pickHead.textContent = (choicePage ? "Jump to an item you haven't picked" : "Jump to an open item") + " · " + all.length.toLocaleString("en-US") + " " + noun + " · showing " + pickShown.length.toLocaleString("en-US");
    pickList.innerHTML = "";
    pickShown.forEach((it, i) => {
      const a = document.createElement("a"); a.href = "#rv-" + it.id; a.setAttribute("role", "option"); a.id = "rvpick-" + i;
      a.innerHTML = '<span class="i"></span><span class="x"></span>';
      a.querySelector(".i").textContent = it.id; a.querySelector(".x").textContent = it.title;
      if (i === pickActive) { a.classList.add("on"); a.setAttribute("aria-selected", "true"); }
      a.addEventListener("click", e => { e.preventDefault(); showIds(false); go(it); });
      pickList.appendChild(a);
    });
    const msg = (cls, text) => { const s = document.createElement("span"); s.className = cls; s.textContent = text; pickList.appendChild(s); };
    if (!all.length) msg("none", choicePage ? "Every item is picked" : "Nothing open");
    else if (!hit.length) msg("nomatch", choicePage ? "No unpicked item matches" : "No open item matches");
    else if (hit.length > pickShown.length) msg("more-n", (hit.length - pickShown.length).toLocaleString("en-US") + " more · keep typing to narrow it");
    if (pickShown.length) pickIn.setAttribute("aria-activedescendant", "rvpick-" + pickActive); else pickIn.removeAttribute("aria-activedescendant");
  }
  pickIn.addEventListener("input", () => { pickActive = 0; renderPicker(); });
  pickIn.addEventListener("keydown", e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault(); if (!pickShown.length) return;
      pickActive = (pickActive + (e.key === "ArrowDown" ? 1 : -1) + pickShown.length) % pickShown.length;
      renderPicker(); const on = pickList.querySelector(".on"); if (on) on.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault(); const it = pickShown[pickActive]; if (it) { showIds(false); go(it); }
    }
  });
  if (store.msg) setStatus(store.msg, store.bad);
  else if (store.loadPending) setStatus("Not saved · retrying", true);
  else if (store.lastMod) setStatus("Saved " + hhmm(store.lastMod));
  if (store.loadPending) persist();

  function lock(it) {
    it.box.querySelectorAll(".seg button, textarea").forEach(x => x.disabled = true);
    it.box.classList.add("locked");
  }
  function save(id) {
    for (const it of items) {
      if (isQ(it) || isC(it) || hidden.has(it.id) || (state[it.id] || {}).locked) continue;
      const v = pressed(it);
      const n = it.box.querySelector("textarea").value;
      state[it.id] = Object.assign({ v, n }, (state[it.id] || {}).blocker ? { blocker: true } : {});
    }
    persist(id); paint();
  }
  const kinds = () => items.map(it => ({ id: it.id, kind: isQ(it) ? "question" : isC(it) ? "choice" : "ync" }));
  let wasDone = null, lastDone = false;
  function setPill(el, text, cls) { el.className = "st" + (cls ? " " + cls : ""); el.textContent = text; }
  function paint() {
    for (const it of items) {
      const s = state[it.id] || {};
      const head = it.card ? it.card.querySelector(":scope > .rvhead") : it.box.querySelector(".rvhead");
      const pill = head.querySelector("[data-pill='1']"), pill2 = head.querySelector("[data-pill='2']");
      if (isQ(it)) continue;
      if (isC(it)) {
        const v = s.v || "";
        it.box.dataset.choice = valOf(it);
        setPressed(it, v);
        it.box.querySelectorAll(".seg button").forEach(b => {
          const isDef = !v && b.dataset.v === it.ch.def;
          b.classList.toggle("def", isDef); b.textContent = b.dataset.label + (isDef ? " (default)" : "");
        });
        const first = it.ch.opts[0][0];
        if (it.card) it.card.dataset.answer = v ? (v === first ? "pick-first" : "pick") : "default";
        if (blocked[it.id]) setPill(pill, "Blocked by " + blocked[it.id], "blk");
        else if (reopen[it.id] && !v) setPill(pill, "Reopened: " + reopen[it.id], "reo");
        else setPill(pill, v ? labelOf(it, v) : it.ch.def ? "Not picked · " + labelOf(it, it.ch.def) + " (default)" : "Not chosen", v ? (v === first ? "a-yes" : "") : "");
        continue;
      }
      const v = s.v || "";
      it.box.classList.remove("yes", "no", "chg", "skip", "empty", "blocker");
      if (v) it.box.classList.add(v);
      if (s.blocker) it.box.classList.add("blocker");
      const noNote = v === "chg" && !(s.n || "").trim();
      if (noNote) it.box.classList.add("empty");
      if (it.card) { it.card.dataset.answer = v; it.card.classList.toggle("is-blocker", !!s.blocker); }
      if (!s.locked) setPressed(it, v);
      if (blocked[it.id]) setPill(pill, "Blocked by " + blocked[it.id], "blk");
      else if (s.locked) setPill(pill, "Skipped (locked)", "skp");
      else if (v) setPill(pill, ANS[v] || v, "a-" + v);
      else if (reopen[it.id]) setPill(pill, "Reopened: " + reopen[it.id], "reo");
      else setPill(pill, "Open", "");
      if (reopen[it.id] && v && !blocked[it.id]) setPill(pill2, "Reopened: " + reopen[it.id], "reo"); else { pill2.className = "st2"; pill2.textContent = ""; }
      if (s.blocker) { pill2.className = "st bkr"; pill2.textContent = "Blocker"; }
      const nl = it.box.querySelector(".notel"), add = it.box.querySelector(".add-note");
      const showNote = v === "chg" || v === "no" || !!(s.n || "").trim() || !!s.blocker || !!it.noteOpen || s.locked;
      nl.hidden = !showNote; add.hidden = showNote || !!s.locked || !!blocked[it.id];
      nl.querySelector(".nlt").textContent = v === "chg" ? "What should change (required)" : v === "no" ? "Why (optional)" : "Note";
    }
    const c = rvCount(kinds(), state, { hidden, blocked });
    const chosen = items.filter(isC);
    const tl = chosen.length ? tally(chosen) : "";
    const qTail = c.qOpen ? " · " + c.qOpen + " question" + (c.qOpen === 1 ? "" : "s") + " unanswered" : "";
    const tails = (c.blocked ? " · " + c.blocked + " blocked" : "") + (c.skipped ? " · " + c.skipped + " skipped" : "") +
      (c.hidden ? " · " + c.hidden + " approved and hidden" : "") + (tl && !c.choiceOnly ? " · " + tl : "") + qTail;
    let text;
    if (c.choiceOnly) text = (c.allDone ? "All " + c.total + " picked" : c.answered + " of " + c.total + " picked") + (tl ? " · " + tl : "") + qTail;
    else if (c.approved) text = "APPROVED · all " + (c.yncTotal || c.hidden) + " Yes" + (c.yncTotal && c.hidden ? " · " + c.hidden + " approved and hidden" : "") + (tl ? " · " + tl : "") + qTail;
    else if (c.allDone) text = "All " + c.total + " answered · ready to copy" + tails;
    else text = c.answered + " of " + c.total + " answered" + tails;
    bar.querySelector(".cnt").textContent = text;
    bar.classList.toggle("all-done", c.allDone);
    bar.classList.toggle("approved", c.approved);
    bar.classList.toggle("has-blocker", c.blockers > 0);
    if (sendBtn) sendBtn.classList.toggle("ready", c.allDone);
    const back = bar.querySelector(".back");
    back.hidden = !(c.allDone && folder); back.href = FOLDER_URL; back.textContent = "\u2190 Back to " + FOLDER_PAGES;
    if (wasDone === false && c.allDone && folder) actToast((c.approved ? "Approved." : "Every item answered.") + " Copy results from More, then", "back to " + FOLDER_PAGES);
    wasDone = c.allDone; lastDone = c.allDone;
    const bkr = bar.querySelector(".bkr");
    bkr.hidden = !c.blockers; bkr.textContent = c.blockers + " BLOCKER" + (c.blockers === 1 ? "" : "S");
    const list = jumpList();
    bar.querySelector(".ids-l").textContent = choicePage ? "Not picked" : "Open IDs";
    bar.querySelector(".ids-n").textContent = "(" + list.length.toLocaleString("en-US") + ")";
    idsBtn.title = choicePage ? "Items you haven't picked yet" : "Find and jump to an open item";
    if (!picker.hidden) renderPicker();
    paintGroupCounts(openList());
  }
  // Unified pages: each group's "N open" chip and the header total count what openList() counts, so
  // they agree with the bar. Pages built before the chips were marked are matched by their text.
  function paintGroupCounts(list) {
    if (!body.classList.contains("unified")) return;
    for (const g of document.querySelectorAll("details.grp")) {
      const chip = g.querySelector("summary [data-open-chip]") ||
        Array.from(g.querySelectorAll("summary .chip")).find(c => /^\d+ open$/.test(c.textContent.trim()));
      if (!chip) continue;
      const mine = items.filter(it => !isQ(it) && it.box.closest("details.grp") === g);
      if (mine.length && mine.every(isC)) {
        chip.textContent = tally(mine);
        chip.classList.remove("c-review", "c-approved");
        continue;
      }
      const n = list.filter(it => it.box.closest("details.grp") === g).length;
      chip.textContent = n + " open";
      chip.classList.toggle("c-review", n > 0); chip.classList.toggle("c-approved", n === 0);
    }
    const tot = document.querySelector("header.top .open-total");
    if (tot) { tot.textContent = list.length; return; }
    const p = document.querySelector("header.top p"), t = p && p.firstChild;
    if (t && t.nodeType === 3 && /^\d+ open items/.test(t.nodeValue)) t.nodeValue = t.nodeValue.replace(/^\d+/, list.length);
  }
  // Open Yes / No / Changes items (what the unified page's group chips count).
  function openList() {
    return items.filter(it => { const s = state[it.id] || {}; return !isQ(it) && !isC(it) && !hidden.has(it.id) && !s.locked && !blocked[it.id] && (!s.v || (s.v === "chg" && !(s.n || "").trim())); });
  }
  // What Previous, Next, n / p and the picker walk: open items plus choice items nobody picked yet.
  function jumpList() {
    const ids = new Set(rvCount(kinds(), state, { hidden, blocked }).openIds);
    return items.filter(it => ids.has(it.id));
  }
  function go(it) {
    const el = it.card || it.nodes[0] || it.box;
    for (let d = el.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) d.open = true; el.scrollIntoView({ behavior: "smooth", block: "start" });
    const f = it.box.querySelector(".seg button:not(:disabled), textarea:not(:disabled)"); if (f) setTimeout(() => f.focus({ preventScroll: true }), 400);
  }
  function step(dir) {
    const list = jumpList(); if (!list.length) return;
    const y = window.scrollY + 80;
    const pos = list.map(it => (it.card || it.nodes[0] || it.box).getBoundingClientRect().top + window.scrollY);
    let i = dir > 0 ? pos.findIndex(t => t > y + 5) : pos.map(t => t < y - 5).lastIndexOf(true);
    if (i < 0) i = dir > 0 ? 0 : list.length - 1;
    go(list[i]);
  }
  bar.querySelector(".next").addEventListener("click", () => step(1));
  bar.querySelector(".prev").addEventListener("click", () => step(-1));
  on(document, "keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target || {}).tagName || "")) return;
    if (e.key === "n") step(1); else if (e.key === "p") step(-1);
  });
  paint();

  const stalePages = (body.getAttribute("data-review-stale") || "").split("|").map(x => x.trim()).filter(Boolean);
  const label = { yes: "YES", no: "NO", chg: "CHANGES", skip: "SKIPPED (locked)" };
  const session = (location.pathname.split("/")[1] || "the").toUpperCase();
  // results() is the whole page; results(group) is one unified-page group (details.grp): its own
  // heading, items, stale line, footer and questions, in the same format.
  function results(group) {
    const src = group && group.getAttribute("data-src");
    const gt = group && group.querySelector("summary .gt");
    const scope = group ? items.filter(it => it.box.closest("details.grp") === group) : items;
    const head = group ? (gt ? gt.textContent.trim() : src) + " (/" + (location.pathname.split("/")[1] || "") + "/" + src + ")" : document.title + " (" + page + ")";
    let out = "Review: " + head + "\n";
    const yncItems = scope.filter(it => !isQ(it) && !isC(it)), qItems = scope.filter(isQ), cItems = scope.filter(isC);
    for (const it of scope.filter(it => !isQ(it))) {
      const s = state[it.id] || {};
      const ans = isC(it) ? (valOf(it) ? labelOf(it, valOf(it)).toUpperCase() : "NOT ANSWERED") : (label[s.v] || "NOT ANSWERED");
      out += "- [" + it.id + "] " + (blocked[it.id] ? "BLOCKED by " + blocked[it.id] + ", " : "") + (s.blocker ? "BLOCKER, " : "") + ans + ": " + it.title + (s.n ? "\n    Note: " + s.n.replace(/\n/g, " ") : "") + "\n";
    }
    for (const p of stalePages) if (!group || p === src) out += "STALE: " + p + "\n";
    const counted = yncItems.filter(it => !(state[it.id] || {}).locked);
    const yes = counted.filter(it => (state[it.id] || {}).v === "yes").length;
    out += "\n";
    if (counted.length || !cItems.length) out += (yes === counted.length ? "APPROVED: every item is Yes." : "Not approved yet: " + yes + " of " + counted.length + " are Yes.") + "\n";
    if (cItems.length) out += tally(cItems) + "\n";
    const qOpen = qItems.filter(it => !((state[it.id] || {}).a || "").trim()).length;
    if (qOpen) out += qOpen + " open question" + (qOpen === 1 ? "" : "s") + "\n";
    // Unified pages prefix ids with their source page ("built.s2"); report each page's approval too.
    const groups = {};
    for (const it of yncItems) { const g = it.id.includes(".") ? it.id.split(".")[0] : ""; if (!g) continue;
      (groups[g] = groups[g] || { n: 0, yes: 0 }).n++; if ((state[it.id] || {}).v === "yes") groups[g].yes++; }
    for (const [g, c] of Object.entries(groups)) out += "  " + g + ": " + (c.yes === c.n ? "APPROVED" : c.yes + " of " + c.n + " Yes") + "\n";
    const cGroups = {};
    for (const it of cItems) { const g = it.id.includes(".") ? it.id.split(".")[0] : ""; if (g && !groups[g]) (cGroups[g] = cGroups[g] || []).push(it); }
    for (const [g, list] of Object.entries(cGroups)) out += "  " + g + ": " + tally(list) + "\n";
    if (qItems.length) {
      out += "\n";
      for (const it of qItems) { const a = ((state[it.id] || {}).a || "").trim(); out += "Q " + it.id + ": " + (a ? a.replace(/\n/g, " ") : "(no answer)") + "\n"; }
    }
    return out;
  }
  async function copyText(out) {
    try { await navigator.clipboard.writeText(out); } catch (e) { const t = document.createElement("textarea"); t.value = out; body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
  }
  bar.querySelector(".copy").addEventListener("click", async () => {
    showMenu(false);
    await copyText(results());
    alert("Copied. Paste it into the " + session + " session.");
    if (lastDone) returnSoon();
  });
  // Copy blockers only: every item marked as a blocker, in the "Blocker: copy now" format.
  bar.querySelector(".copy-blockers").addEventListener("click", async () => {
    showMenu(false);
    const list = items.filter(it => !isQ(it) && !hidden.has(it.id) && (state[it.id] || {}).blocker);
    if (!list.length) { alert("No item on this page is marked as a blocker."); return; }
    const build = body.getAttribute("data-build");
    let out = "BLOCKER: " + document.title + " (" + page + (build ? ", build " + build : "") + ")\n";
    for (const it of list) out += "- [" + it.id + "] " + it.title + "\n    Note: " + ((state[it.id] || {}).n || "").replace(/\n/g, " ") + "\n";
    await copyText(out);
    alert(list.length + (list.length === 1 ? " blocker" : " blockers") + " copied. Paste " + (list.length === 1 ? "it" : "them") + " to " + BLOCKER_TO + " now.");
  });
  // Unified pages: a Copy button next to each group's "N open" chip copies just that group. It sits
  // inside <summary>, so the click must stop there or it would toggle the group.
  if (body.classList.contains("unified")) for (const g of document.querySelectorAll("details.grp")) {
    const gm = g.querySelector("summary .gm"); if (!gm || gm.querySelector(".grp-copy")) continue;
    const chip = gm.querySelector("[data-open-chip]") || Array.from(gm.querySelectorAll(".chip")).find(c => /^\d+ open$/.test(c.textContent.trim()));
    const b = document.createElement("button"); b.type = "button"; b.className = "grp-copy"; b.textContent = "Copy";
    b.title = "Copy this page's results only";
    b.addEventListener("click", async e => {
      e.preventDefault(); e.stopPropagation();
      await copyText(results(g));
      b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500);
    });
    if (chip) chip.after(b); else gm.prepend(b);
  }
  // Fills only unanswered Yes / No / Changes items, so a Changes note or an earlier pick is never overwritten.
  function markAll(v, label) {
    showMenu(false);
    const open = items.filter(it => !isQ(it) && !isC(it) && !hidden.has(it.id) && !blocked[it.id] && !(state[it.id] || {}).locked && !pressed(it));
    if (!open.length) { alert("Every item already has an answer."); return; }
    if (!confirm("Mark the " + open.length + " unanswered item" + (open.length === 1 ? "" : "s") + " " + label + "? Items you've answered keep their answers.")) return;
    for (const it of open) { setPressed(it, v); store.touched.add(it.id); }
    save();
  }
  bar.querySelector(".all-yes").addEventListener("click", () => markAll("yes", "Yes"));
  bar.querySelector(".all-no").addEventListener("click", () => markAll("no", "No"));
  bar.querySelector(".clear").addEventListener("click", async () => {
    showMenu(false);
    if (!confirm("Clear your answers on this page? Approved and Skipped (locked) items stay.")) return;
    for (const it of items) if (!hidden.has(it.id) && !(state[it.id] || {}).locked) { delete state[it.id]; store.touched.add(it.id); }
    persist();
    if (await flushNow()) { if (PF) PF.redraw(); else location.reload(); }
    else { paint(); alert("Cleared here, but the box can't be reached yet. It keeps retrying; don't close the page until it says Saved."); }
  });
  // ---------- round history (/_history/<page-key>/, see SAVE-API.md) ----------
  // Collapsed everywhere: the block itself starts closed, and so does every round inside it.
  // Nothing here is ever expanded automatically, and it always sits after the page's own content,
  // so it never pushes the current round's open items down.
  let histBlock = null;
  const historyBtn = bar.querySelector(".history");
  function renderHistory(data) {
    const outer = document.createElement("details"); outer.className = "rvhist";
    const n = data.rounds.length;
    const summary = document.createElement("summary");
    summary.textContent = "History (" + n + (n === 1 ? " round" : " rounds") + ")" + (data.page_removed ? " · page removed" : "");
    outer.appendChild(summary);
    for (const r of data.rounds) {
      const d = document.createElement("details"); d.className = "rvhist-round";
      const s = document.createElement("summary");
      s.textContent = "Round " + r.round + (r.build ? " · build " + r.build : "") + " · " + (r.closed || "").slice(0, 10) + " · " + r.count;
      d.appendChild(s);
      const pre = document.createElement("pre"); pre.className = "hist-text";
      const cp = document.createElement("button"); cp.type = "button"; cp.className = "hist-copy"; cp.textContent = "Copy results"; cp.disabled = true;
      d.append(pre, cp);
      d.addEventListener("toggle", async () => {
        if (!d.open || d.dataset.loaded) return;
        d.dataset.loaded = "1";
        // A page file's rounds carry their text; an HTML page's history entry is fetched.
        let text = r.results;
        if (text === undefined) {
          pre.textContent = "Loading...";
          try { text = (await (await fetch(HIST_URL + r.file, { cache: "no-store" })).json()).results_text || ""; }
          catch (e) { pre.textContent = "Couldn't load this round."; return; }
        }
        pre.textContent = text;
        cp.disabled = false;
        cp.addEventListener("click", async () => {
          try { await navigator.clipboard.writeText(text); } catch (e) { const ta = document.createElement("textarea"); ta.value = text; body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); }
          cp.textContent = "Copied"; setTimeout(() => { cp.textContent = "Copy results"; }, 1500);
        });
      });
      outer.appendChild(d);
    }
    if (histBlock) histBlock.replaceWith(outer); else body.appendChild(outer);
    histBlock = outer;
    historyBtn.disabled = !n;
  }
  async function loadHistory() {
    try {
      const r = await fetch(HIST_URL, { cache: "no-store" });
      if (r.ok) renderHistory(await r.json());
    } catch (e) { /* offline: History stays disabled until the next load */ }
  }
  if (PF) renderHistory(PF.history()); else loadHistory();
  historyBtn.addEventListener("click", () => {
    showMenu(false);
    if (!histBlock) return;
    histBlock.open = true;
    histBlock.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  bar.querySelector(".round-close").addEventListener("click", async () => {
    showMenu(false);
    if (!confirm("Save this round to history now? The next change starts a new round.")) return;
    if (!(await flushNow())) { alert("Can't save yet: the box can't be reached. Try again once it says Saved."); return; }
    if (PF) {
      try {
        const out = await PF.closeRound(results());
        await PF.redraw();
        alert("Saved as Round " + (out.round - 1) + ".");
      } catch (e) { alert("Couldn't save the round: " + e.message); }
      return;
    }
    try {
      const r = await fetch("/_round-close", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: HIST_NAME, results_text: results() }), cache: "no-store" });
      const out = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(out.error || ("HTTP " + r.status));
      await loadHistory();
      alert("Saved as Round " + out.round + ".");
    } catch (e) { alert("Couldn't save the round: " + e.message); }
  });

  if (sendBtn) sendBtn.addEventListener("click", async () => {
    const c = rvCount(kinds(), state, { hidden, blocked });
    const left = c.total - c.answered;
    if (!c.allDone && !confirm("Send now? " + left + " item" + (left === 1 ? " is" : "s are") + " still open.")) return;
    if (!(await flushNow())) { alert("Can't send yet: the answers aren't saved. Try again once it says Saved."); return; }
    try {
      const sent = await PF.send("send", null, results());
      setDelivery("Sent " + hhmm(new Date()) + (sent.listening ? "" : " · " + sent.to + " isn't listening; Copy results instead"));
    } catch (e) { alert("Couldn't send: " + e.message + ". Use Copy results instead."); }
  });
  // Before a redraw: take this page's listeners, bar, notes and History off, so mounting again starts clean.
  function unmount() {
    offs.splice(0).forEach(off => off());
    clearTimeout(store.timer); store.timer = null;
    if (backTimer) { clearTimeout(backTimer); backTimer = null; }
    bar.remove();
    if (histBlock) histBlock.remove();
    document.querySelectorAll(".rvdone, .site-toast.act").forEach(x => x.remove());
  }
  window.siteReview = { results, unsaved, saveUrl: SAVE_URL, state: () => state, flushNow, unmount };
  const target = location.hash && document.getElementById(location.hash.slice(1));
  if (target) for (let d = target.closest("details"); d; d = d.parentElement && d.parentElement.closest("details")) d.open = true;

  loadLive();
  }

  function loadLive() {
    if (document.querySelector('script[src*="/_site/live.js"]')) return;
    const sc = document.createElement("script"); sc.src = "/_site/live.js?v=22"; sc.setAttribute("data-mode", PF ? "file" : "page"); body.appendChild(sc);
  }
})();

// Diff blocks: a Diff / Final switch per block, and one for the whole page when it has several. Final hides
// removed text and shows the rest plainly. The choice is kept for this tab, so a live reload doesn't undo it.
// render.js runs it again after each redraw (window.siteDiff); blocks that already have a switch are left alone.
window.siteDiff = function () {
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
};
window.siteDiff();

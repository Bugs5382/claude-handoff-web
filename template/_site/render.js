// Renderer for page files (handoff.page/v1, see PAGE-FILE.md). The shell (_site/page.html) loads this script;
// it fetches GET /_page/<folder>/<slug> and draws the page into the same DOM and classes the HTML pages use:
// each answerable item is a <section data-review-question> card, the page's settings are body data-*
// attributes, how-tos are <template data-howto>. review.js then adds the answer controls and the bar, and
// saves through window.sitePage instead of /_save/.
// Live: the page is polled every 10 s with If-None-Match. A new version is redrawn in place, never while
// someone is typing, within 3 s of a click, or while answers are still unsaved; the scroll position is kept.
// When the only change is this tab's own answers coming back, nothing is redrawn.
(function () {
  const POLL = 10000, IDLE = 3000;
  const rel = decodeURIComponent(location.pathname).replace(/^\/+|\/+$/g, "");
  const API = "/_page/" + rel;
  const ANS_IN = { yes: "yes", no: "no", changes: "chg", skipped: "skip" };
  const ANS_OUT = { yes: "yes", no: "no", chg: "changes", skip: "skipped" };
  const ANS_LABEL = { yes: "Yes", no: "No", changes: "Changes", skipped: "Skipped" };
  // The answers each type offers, as review.js names them (pagefile.allowed_answers is the server's copy).
  const TYPE_ANSWERS = { section: ["yes", "no", "chg"], screen: ["yes", "no", "chg"], contract: ["yes", "no", "chg"], diff: ["yes", "no", "chg"],
    check: ["yes", "no", "chg", "skip"], step: ["yes", "no", "chg", "skip"] };
  const TYPE_BY_KIND = { review: "section", checklist: "check", journey: "step", backlog: "choice", questions: "question", reference: "info", status: "info" };
  let data = null, etag = null, baseline = {}, lastAct = 0, pending = null, reviewLoaded = false;

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  // Inline markup, escape first: **bold**, *em*, `code` and [text](url) with a plain http(s), relative or # link.
  function inline(s) {
    return String(s || "").split(/(`[^`]*`)/).map(part => {
      if (/^`[^`]*`$/.test(part)) return "<code>" + esc(part.slice(1, -1)) + "</code>";
      let h = esc(part);
      h = h.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => /^(https?:\/\/|\/|\.|#|[a-z0-9])/i.test(u) && !/^javascript:/i.test(u) ? '<a href="' + u + '">' + t + "</a>" : m);
      h = h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
      return h;
    }).join("");
  }
  const typeOf = it => it.type || TYPE_BY_KIND[data.page.kind];
  const answerable = it => typeOf(it) !== "info";
  const hhmm = iso => { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }); };
  const when = iso => String(iso || "").slice(0, 16).replace("T", " ");

  function block(b, key) {
    if ("p" in b) return "<p>" + inline(b.p) + "</p>";
    if ("list" in b) return "<ul>" + b.list.map(x => "<li>" + inline(x) + "</li>").join("") + "</ul>";
    if ("olist" in b) return "<ol>" + b.olist.map(x => "<li>" + inline(x) + "</li>").join("") + "</ol>";
    if ("code" in b) return "<pre>" + esc(b.code) + "</pre>";
    if ("image" in b) return "<p>" + picture(b) + "</p>";
    if ("table" in b) return "<table><thead><tr>" + b.table[0].map(c => "<th>" + inline(c) + "</th>").join("") + "</tr></thead><tbody>" +
      b.table.slice(1).map(r => "<tr>" + r.map(c => "<td>" + inline(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>";
    if ("diff" in b) return (data.diffs || {})[key] || "";
    if ("copy" in b) return '<div class="copyblk"><pre>' + esc(b.copy) + '</pre><button type="button" class="copy-cmd">Copy</button></div>';
    if ("note" in b) return '<p class="note ' + esc(b.tone || "info") + '">' + inline(b.note) + "</p>";
    if ("html" in b) return '<div class="raw-html" data-flagged="unconverted">' + b.html + "</div>";
    return "";
  }
  function picture(b) {
    return '<a href="' + esc(b.image) + '" target="_blank" rel="noopener"><img src="' + esc(b.image) + '" alt="' + esc(b.alt || "") + '" width="320"></a>' +
      (b.caption ? '<br><span class="muted">' + inline(b.caption) + "</span>" : "");
  }
  // Pictures in a row share one paragraph, so they sit side by side as they do on an HTML page.
  function blocks(list, id, key) {
    let out = "", row = [];
    const flush = () => { if (row.length) out += "<p>" + row.join("\n") + "</p>"; row = []; };
    (list || []).forEach((b, i) => {
      if ("image" in b && !b.caption) { row.push(picture(b)); return; }
      flush(); out += block(b, id + "/" + key + "/" + (i + 1));
    });
    flush();
    return out;
  }
  function fieldsTable(fields) {
    return "<table><thead><tr><th>Name</th><th>Type</th><th>Rule</th></tr></thead><tbody>" +
      fields.map(f => "<tr><td>" + inline(f.name) + "</td><td>" + inline(f.type || "") + "</td><td>" + inline(f.rule || "") + "</td></tr>").join("") + "</tbody></table>";
  }

  // My answers from closed rounds and the replies, oldest first, under each item.
  function threadHtml(id) {
    const rows = [];
    const rounds = data.page.rounds;
    for (const r of rounds.slice(0, -1)) {
      const a = r.answers[id]; if (!a || (!a.answer && !a.note)) continue;
      const label = ANS_LABEL[a.answer] || a.answer;
      rows.push({ at: a.at, html: "<b>Round " + r.round + " · you</b> <span class=\"muted\">" + esc(when(a.at)) + "</span> " + esc([label, a.note].filter(Boolean).join(": ")) });
    }
    for (const x of (data.page.thread || {})[id] || []) {
      rows.push({ at: x.at, html: "<b>" + esc(x.from) + (x.action ? " · " + esc(x.action) : "") + "</b> <span class=\"muted\">" + esc(when(x.at)) + "</span> " + inline(x.text) });
    }
    if (!rows.length) return "";
    rows.sort((a, b) => String(a.at).localeCompare(String(b.at)));
    return '<div class="rvthread">' + rows.map(r => "<p>" + r.html + "</p>").join("") + "</div>";
  }

  // What blocks an item, the way the server counts it: a blockedBy with no unblock reply, or a dependsOn
  // that isn't Yes (a journey step depends on the step before it unless it says otherwise).
  function blockers() {
    const out = {}, st = data.states, thread = data.page.thread || {};
    let prevStep = null;
    for (const it of data.page.items) {
      const t = typeOf(it);
      if (t === "info") continue;
      let deps = it.dependsOn;
      if (deps === undefined) deps = t === "step" && prevStep ? [prevStep] : [];
      if (t === "step") prevStep = it.id;
      if (it.blockedBy && !(thread[it.id] || []).some(r => r.action === "unblock")) out[it.id] = it.blockedBy;
      else { const d = deps.find(x => ((st[x] || {}).answer || "") !== "yes"); if (d) out[it.id] = d; }
    }
    return out;
  }

  function itemHtml(it, n) {
    const t = typeOf(it), id = esc(it.id);
    let inner = "<h2>" + n + ". " + esc(it.title) + "</h2>";
    if (it.steps) inner += "<ol>" + it.steps.map(s => "<li>" + inline(s) + "</li>").join("") + "</ol>";
    if (t === "diff") inner += (data.diffs || {})[it.id] || "";
    if (it.images) inner += it.images.map(im => block({ image: im.src, alt: im.alt, caption: im.caption })).join("");
    if (it.fields) inner += fieldsTable(it.fields);
    if (it.forms) inner += it.forms.map(f => '<p><strong>' + esc(f.name) + "</strong></p>" + fieldsTable(f.fields || [])).join("");
    inner += blocks(it.body, it.id, "body");
    if (it.howto) inner += "<template data-howto>" + blocks(it.howto, it.id, "howto") + "</template>";
    inner += threadHtml(it.id);
    const group = it.section ? '<h2 class="group-h">' + esc(it.section) + "</h2>" : "";
    if (!answerable(it)) return group + '<section class="info" data-item="' + id + '">' + inner + "</section>";
    // Each item carries its own answers, so one page can mix sections, questions, choices and steps.
    let q = "";
    if (t === "question") q = ' data-review-type="question"' + (it.suggested ? ' data-suggested="' + esc(it.suggested) + '"' : "");
    else if (t === "choice") q = ' data-review-options="' + esc(data.page.options.choices.map(c => c.value + ":" + c.label).join(",")) + '"' +
      (data.page.options.default ? ' data-review-default="' + esc(data.page.options.default) + '"' : "");
    else {
      let set = it.answers ? it.answers.map(a => ANS_IN[a] || a) : TYPE_ANSWERS[t].slice();
      if (it.skip && !set.includes("skip")) set = set.concat("skip");
      q = ' data-review-answers="' + esc(set.join(",")) + '"';
    }
    return group + '<section data-item="' + id + '" data-review-question="' + id + '" data-title="' + esc(it.title) + '"' + q + ">" + inner + "</section>";
  }

  function render() {
    const p = data.page, body = document.body;
    document.title = p.title;
    for (const a of Array.from(body.attributes)) if (a.name.startsWith("data-")) body.removeAttribute(a.name);
    const set = (k, v) => { if (v !== undefined && v !== null && v !== "") body.setAttribute(k, v); };
    set("data-review-h2", "off");
    set("data-review-page", "/" + rel);
    set("data-build", p.build);
    if (p.kind === "reference" || p.kind === "status") set("data-review-controls", "off");
    const bl = blockers();
    set("data-review-blocked", Object.entries(bl).map(([k, v]) => k + "=" + v).join("|"));
    set("data-review-approved", Object.entries(data.states).filter(([, s]) => s.hidden).map(([k]) => k).join(","));
    set("data-review-reopen", Object.entries(data.states).filter(([, s]) => s.reopened).map(([k, s]) => k + "=" + s.reopened).join("|"));
    let top = body.querySelector("header.top");
    if (!top) { top = document.createElement("header"); top.className = "top"; body.prepend(top); }
    // The theme toggle (theme.js) lives in the header; carry it across the redraw.
    const toggle = top.querySelector(".theme-tg");
    top.innerHTML = '<div class="wrap"><h1>' + esc(p.title) + "</h1>" + (p.summary ? "<p>" + inline(p.summary) + "</p>" : "") + "</div>";
    if (toggle) top.appendChild(toggle);
    let main = body.querySelector("main");
    if (!main) { main = document.createElement("main"); main.className = "wrap"; top.after(main); }
    main.id = "page";
    const pageThread = ((p.thread || {})._page || []).map(x => "<p><b>" + esc(x.from) + "</b> <span class=\"muted\">" + esc(when(x.at)) + "</span> " + inline(x.text) + "</p>").join("");
    let restart = "";
    if (p.kind === "journey") {
      const reached = [];
      for (const r of p.rounds) for (const cp of Object.keys(r.checkpoints || {})) if (!reached.includes(cp)) reached.push(cp);
      if (reached.length) restart = '<p class="rvrestart">Restart from: ' + reached.map(cp => '<button type="button" data-cp="' + esc(cp) + '">' + esc(cp) + "</button>").join(" ") + "</p>";
    }
    main.innerHTML = (pageThread ? '<div class="rvthread page-thread">' + pageThread + "</div>" : "") + restart +
      p.items.map((it, i) => itemHtml(it, i + 1)).join("");
  }

  // ---------- the storage review.js uses on a page file ----------
  function toState() {
    const p = data.page, r = p.rounds[p.rounds.length - 1], state = {};
    const items = Object.fromEntries(p.items.map(it => [it.id, it]));
    for (const [id, a] of Object.entries(r.answers)) {
      const it = items[id]; if (!it) continue;
      const t = typeOf(it);
      if (t === "question") state[id] = { a: a.answer || "" };
      else if (t === "choice") state[id] = { v: a.answer || "", n: a.note || "" };
      else { state[id] = { v: ANS_IN[a.answer] || "", n: a.note || "" }; if (a.answer === "skipped") state[id].locked = true; }
    }
    for (const s of p.submissions || []) {
      if (s.kind !== "blocker" || s.round !== r.round) continue;
      for (const id of s.items || []) state[id] = Object.assign({ v: "", n: "" }, state[id] || {}, { blocker: true });
    }
    return state;
  }
  function toAnswer(id, s) {
    const it = data.page.items.find(x => x.id === id), t = typeOf(it);
    s = s || {};
    if (t === "question") return { answer: s.a || "", note: "" };
    if (t === "choice") return { answer: s.v || "", note: s.n || "" };
    return { answer: ANS_OUT[s.v] || "", note: s.n || "" };
  }
  // What this tab changed since the last save, item by item. Changes without a note waits for its note, since the
  // server refuses it; hidden Yes items from earlier rounds are never written into the open round.
  function changes(state) {
    const ids = new Set(data.page.items.filter(answerable).map(it => it.id));
    const out = {};
    for (const id of ids) {
      if ((data.states[id] || {}).hidden) continue;
      const a = toAnswer(id, state[id]), b = toAnswer(id, baseline[id]);
      if (a.answer === b.answer && a.note === b.note) continue;
      if (a.answer === "changes" && !a.note.trim()) continue;
      out[id] = a;
    }
    return out;
  }
  const post = async (path, body) => {
    const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
    const out = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((out.errors || [out.error || "HTTP " + r.status]).join("; "));
    return out;
  };
  function lastSaved() {
    const r = data.page.rounds[data.page.rounds.length - 1];
    const ats = Object.values(r.answers).map(a => a.at).filter(Boolean).sort();
    return ats.length ? new Date(ats[ats.length - 1]) : null;
  }

  window.sitePage = {
    rel,
    get route() { return data.route; },
    get listening() { return data.listening; },
    get items() {
      return Array.from(document.querySelectorAll("main section[data-review-question]")).map(el => ({
        id: el.getAttribute("data-review-question"), title: el.getAttribute("data-title"), el,
        type: el.getAttribute("data-review-type") || "", suggested: el.getAttribute("data-suggested") || ""
      }));
    },
    lastSaved,
    state() { const s = toState(); baseline = JSON.parse(JSON.stringify(s)); return s; },
    async save(state) {
      const ch = changes(state);
      if (!Object.keys(ch).length) return;
      const r = await fetch(API + "/answers", { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base: data.page.rev, answers: ch }), cache: "no-store" });
      if (r.status !== 200) throw new Error("PUT " + r.status);
      for (const id of Object.keys(ch)) baseline[id] = JSON.parse(JSON.stringify(state[id] || {}));
    },
    saveKeepalive(state) {
      const ch = changes(state);
      if (Object.keys(ch).length) fetch(API + "/answers", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers: ch }), keepalive: true });
    },
    send: (kind, items, results) => post("/send", { kind, items: items || undefined, results }),
    closeRound: results => post("/round", { results }),
    restart: (checkpoint, results) => post("/restart", { checkpoint, results }),
    // Closed rounds for review.js's History block, newest first, with their Copy results text inline.
    history() {
      const items = data.page.items.filter(it => answerable(it) && typeOf(it) !== "question" && typeOf(it) !== "choice");
      const rounds = data.page.rounds.filter(r => r.closed).map(r => {
        const yes = items.filter(it => (r.answers[it.id] || {}).answer === "yes").length;
        return { round: r.round, build: r.build || "", closed: r.closed, count: items.length ? yes + " of " + items.length + " Yes" : "no items", results: r.results || "" };
      }).reverse();
      return { page_removed: false, rounds };
    },
    // The bar's delivery line for the latest Send or Blocker.
    delivery() {
      const subs = data.page.submissions || [];
      const s = subs[subs.length - 1]; if (!s) return "";
      const to = s.to || data.route.to;
      let text = s.state === "taken" ? "Picked up by " + to + " " + hhmm(s.takenAt) : "Sent " + hhmm(s.at);
      const reply = ((data.page.thread || {})._page || []).filter(x => x.at > s.at).pop();
      if (reply) text += " · " + reply.from + " replied " + hhmm(reply.at);
      else if (s.state !== "taken" && !data.listening) text += " · " + to + " isn't listening; Copy results instead";
      return text;
    },
    redraw: () => refresh(true)
  };

  // ---------- loading and live redraw ----------
  async function fetchPage(force) {
    const r = await fetch(API, { cache: "no-store", headers: !force && etag ? { "If-None-Match": etag } : {} });
    if (r.status === 304) return null;
    if (!r.ok) throw new Error("GET " + r.status);
    etag = r.headers.get("ETag");
    return await r.json();
  }
  function typing() {
    const a = document.activeElement;
    return !!a && (a.tagName === "TEXTAREA" || a.isContentEditable || (a.tagName === "INPUT" && !/^(radio|checkbox|button|submit|reset)$/i.test(a.type)));
  }
  // Only this tab's own answers came back: keep the page as it is and move the baseline on.
  function onlyMine(next) {
    const strip = d => { const c = JSON.parse(JSON.stringify(d.page)); delete c.rev; c.rounds[c.rounds.length - 1].answers = {}; return JSON.stringify([c, d.route, d.listening]); };
    if (strip(next) !== strip(data)) return false;
    const prev = data; data = next;
    const mine = window.siteReview && window.siteReview.state ? window.siteReview.state() : null;
    const theirs = toState();
    const ids = data.page.items.filter(answerable).map(it => it.id).filter(id => !(data.states[id] || {}).hidden);
    const same = mine && ids.every(id => { const a = toAnswer(id, mine[id]), b = toAnswer(id, theirs[id]); return a.answer === b.answer && a.note === b.note; });
    if (!same) { data = prev; return false; }
    baseline = JSON.parse(JSON.stringify(theirs));
    return true;
  }
  function draw() {
    const x = scrollX, y = scrollY;
    if (window.siteReview && window.siteReview.unmount) window.siteReview.unmount();
    render();
    if (window.siteReviewMount) window.siteReviewMount();
    if (window.siteDiff) window.siteDiff();
    scrollTo(x, y);
  }
  async function refresh(force) {
    const next = force ? await fetchPage(true) : (pending || await fetchPage(false));
    if (!next) return;
    if (!force && (typing() || Date.now() - lastAct < IDLE || (window.siteReview && window.siteReview.unsaved && window.siteReview.unsaved()))) { pending = next; return; }
    pending = null;
    if (!force && onlyMine(next)) return;
    data = next;
    draw();
  }
  function loadScript(src, attrs) {
    const sc = document.createElement("script"); sc.src = src;
    for (const [k, v] of Object.entries(attrs || {})) sc.setAttribute(k, v);
    document.body.appendChild(sc);
  }
  document.addEventListener("click", async e => {
    const cp = e.target.closest && e.target.closest(".copyblk .copy-cmd");
    if (cp) {
      const text = cp.previousElementSibling.textContent;
      try { await navigator.clipboard.writeText(text); } catch (err) { const t = document.createElement("textarea"); t.value = text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); }
      cp.textContent = "Copied"; setTimeout(() => { cp.textContent = "Copy"; }, 1500);
      return;
    }
    const rs = e.target.closest && e.target.closest(".rvrestart button[data-cp]");
    if (rs) {
      if (!confirm("Restart from " + rs.dataset.cp + "? Steps after it start open again, and the restart is sent to " + data.route.to + ".")) return;
      try {
        if (window.siteReview && window.siteReview.flushNow) await window.siteReview.flushNow();
        await window.sitePage.restart(rs.dataset.cp, window.siteReview ? window.siteReview.results() : "");
        await refresh(true);
      } catch (err) { alert("Couldn't restart: " + err.message); }
    }
  });
  for (const ev of ["input", "change", "keydown", "pointerdown", "click"]) document.addEventListener(ev, () => { lastAct = Date.now(); }, true);

  (async function boot() {
    try { data = await fetchPage(true); } catch (e) {
      document.querySelector("main").innerHTML = '<p class="muted">This page couldn\'t be loaded. It retries in a moment.</p>';
      setTimeout(boot, POLL); return;
    }
    render();
    if (!reviewLoaded) { reviewLoaded = true; loadScript("/_site/review.js?v=27"); }
    setInterval(() => { if (!document.hidden) refresh(false).catch(() => {}); }, POLL);
  })();
})();

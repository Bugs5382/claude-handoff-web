#!/usr/bin/env python3
"""Rebuild index.html for the web root and each folder from <folder>/_status.json.

Each manifest maps a page path (relative to its folder: "x.html", "dir/", "dir/y.html") to
{"state": "needs-you"|"reference"|"done", "note": "...", "chips": ["Decision needed"]}.
"first_seen" is added automatically the first time a page is met. Pages that exist but are not in
the manifest show under "Needs you" with a "Not classified" chip, so nothing hides silently.
Names, folders, blurbs and the timezone come from site.json next to this script. See _site/README.md.
Page files (<folder>/<slug>.json, see _site/PAGE-FILE.md) are listed too, from the files themselves, so a folder
with only page files needs no _status.json. serve.py builds the same pages on request for folders with page files.
"""
import datetime as dt
import html
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "_site"))
import pagefile  # noqa: E402
import pageindex  # noqa: E402

HISTORY_NOTE = "Past review and sign-off rounds for this folder."
def _config():
    with open(os.path.join(ROOT, "site.json")) as f:
        return json.load(f)


CONFIG = _config()
FOLDERS = {f["id"]: f["name"] for f in CONFIG["folders"]}
BLURB = {f["id"]: f.get("blurb", "") for f in CONFIG["folders"]}
PROTECTED = set(CONFIG.get("protected", []))
ET = ZoneInfo(CONFIG.get("timezone", "UTC"))
TZ_LABEL = CONFIG.get("tz_label", CONFIG.get("timezone", "UTC"))
SECTIONS = [("needs-you", "Needs you"), ("reference", "Reference"), ("done", "Completed")]
CHIP_CLASS = {"New": "c-new", "Updated": "c-updated", "To review": "c-review", "Reopened": "c-reopened",
              "Approved": "c-approved", "Reference": "c-reference", "Done": "c-done",
              "Not classified": "c-unclassified"}
esc = html.escape


def asset(name):
    p = os.path.join(ROOT, "_site", name)
    return f"/_site/{name}?v={int(os.path.getmtime(p))}"


def target(folder, key):
    full = os.path.join(ROOT, folder, key.rstrip("/"))
    if key.endswith("/"):
        idx = os.path.join(full, "index.html")
        return idx if os.path.exists(idx) else full
    return full


def mtime(p):
    if os.path.isdir(p):
        ts = [os.path.getmtime(os.path.join(p, e)) for e in os.listdir(p) if not e.startswith(".")]
        return max(ts or [os.path.getmtime(p)])
    return os.path.getmtime(p)


def read(p):
    try:
        return open(p, errors="ignore").read() if os.path.isfile(p) else ""
    except OSError:
        return ""


def title_of(src, key):
    for pat in (r"<title>(.*?)</title>", r"<h1[^>]*>(.*?)</h1>"):
        m = re.search(pat, src, re.S | re.I)
        if m:
            t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            if t:
                return re.sub(r"\s+", " ", t)
    return key


def review_info(src):
    """Count review.js items on a page the way its bottom bar does: (items, open, reopened, choice items).
    None if the page has no review.js. Open questions are never items; choice items (the page's own
    data-review-options) are never open, and neither are approved or blocked (data-review-blocked) items."""
    if "review.js" not in src:
        return None
    m = re.search(r"<body[^>]*>", src)
    body = m.group(0) if m else ""
    get = lambda n: html.unescape((re.search(n + r'="([^"]*)"', body) or [None, ""])[1])
    reopen = {p.split("=", 1)[0].strip() for p in get("data-review-reopen").split("|") if "=" in p}
    approved = {a.strip() for a in get("data-review-approved").split(",") if a.strip()} - reopen
    blocked = {p.split("=", 1)[0].strip() for p in get("data-review-blocked").split("|") if "=" in p}
    if get("data-review-controls") == "off":
        return None
    inner = re.sub(r"<script.*?</script>", "", src[m.end():] if m else src, flags=re.S)
    h2s = [] if get("data-review-h2") == "off" else re.findall(r"<h2(?:\s[^>]*)?>", inner)
    tags = [(f"s{i}", t) for i, t in enumerate(h2s, 1)]
    tags += [(html.unescape(q.group(1)), q.group(0))
             for q in re.finditer(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*\bdata-review-question="([^"]*)"[^>]*>', inner)]
    tags = [(i, t) for i, t in tags if 'data-review-type="question"' not in t]
    page_choices = bool(get("data-review-options").strip())
    choice = {i for i, t in tags if page_choices or "data-review-options=" in t}
    ync = [i for i, _ in tags if i not in choice]
    open_n = sum(1 for i in ync if i not in approved and i not in blocked)
    return len(tags), open_n, len(reopen), len(choice)


def when(ts):
    d = dt.datetime.fromtimestamp(ts, ET)
    return d.strftime("%b %-d, %-I:%M %p ") + TZ_LABEL


def is_page_dir(p):
    """A subfolder is a page only when it holds an .html file; img/ and other asset folders never are."""
    try:
        return any(e.endswith(".html") for e in os.listdir(p))
    except OSError:
        return False


def discover(folder):
    fp = os.path.join(ROOT, folder)
    keys = []
    for e in sorted(os.listdir(fp)):
        if e.startswith(("_", ".")) or e == "index.html":
            continue
        full = os.path.join(fp, e)
        if os.path.isdir(full):
            if is_page_dir(full):
                keys.append(e + "/")
        elif e.endswith(".html"):
            keys.append(e)
    return keys


def collect(folder):
    fp = os.path.join(ROOT, folder)
    os.makedirs(fp, exist_ok=True)
    mpath = os.path.join(fp, "_status.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    found = discover(folder)
    keys = found + [k for k in manifest if k not in found and os.path.exists(target(folder, k))
                    and not (os.path.isdir(target(folder, k)) and not is_page_dir(target(folder, k)))]
    dirty, pages = False, []
    for k in keys:
        p = target(folder, k)
        mt = mtime(p)
        ent = manifest.get(k)
        known = ent is not None
        if not known and k == "history/":
            # gen-index.py's own history page is always Reference, with or without a manifest entry.
            ent, known = {"state": "reference", "note": HISTORY_NOTE, "first_seen": dt.datetime.fromtimestamp(mt, ET).isoformat(timespec="seconds")}, True
        elif not known:
            ent = {}
        if "first_seen" not in ent:
            ent["first_seen"] = dt.datetime.fromtimestamp(min(mt, dt.datetime.now().timestamp()), ET).isoformat(timespec="seconds")
            manifest[k] = ent
            dirty = True
        state = ent.get("state") if known and ent.get("state") in dict(SECTIONS) else "needs-you"
        src = read(p)
        chips = []
        if not known or "state" not in ent:
            chips.append("Not classified")
        if state == "needs-you":
            chips.append("To review")
        info = review_info(src)
        # A page whose items are all its own answer choices has nothing "open" to count.
        open_items = info[1] if info and state == "needs-you" and info[0] > info[3] else None
        if info and state == "needs-you":
            n, open_n, reo, n_choice = info
            if reo:
                chips.append("Reopened")
            if open_n and "To review" not in chips:
                chips.append("To review")
            if n > n_choice and not open_n:
                chips.append("Approved")
        chips.append({"reference": "Reference", "done": "Done"}.get(state, ""))
        chips += [c for c in ent.get("chips", []) if c]
        chips = [c for i, c in enumerate(chips) if c and c not in chips[:i]]
        first = dt.datetime.fromisoformat(ent["first_seen"]).timestamp()
        tally = choice_tally(folder, k, src, info) if info and state == "needs-you" and info[3] and info[0] == info[3] else None
        pages.append(dict(folder=folder, key=k, href=f"/{folder}/{k}", title=title_of(src, k), note=ent.get("note", ""),
                          state=state, chips=chips, mtime=mt, first=first, open=open_items, priority=ent.get("priority", 50),
                          tally=tally))
    if dirty:
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
    pages += [pageindex.page_card(folder, rel, path) for rel, path in pageindex.discover_page_files(ROOT, folder)]
    return order_pages(pages, list(manifest))


def choice_tally(folder, key, src, info):
    """The per-choice counts a choices page's bar shows ("2 start · 21 hold"), from its saved answers
    (_saved/<page-key>.json): an item nobody picked counts as the page's default."""
    choices = page_choices(src)
    if not choices:
        return None
    name = page_key(CONFIG.get("key_prefix", "review:") + f"/{folder}/{key}")
    try:
        answers = json.load(open(os.path.join(ROOT, "_saved", name + ".json")))
    except (OSError, ValueError):
        answers = {}
    ids = set(choice_ids(src))
    answers = {k: v for k, v in (answers if isinstance(answers, dict) else {}).items() if k in ids}
    return round_count_line(answers, choices, info[3])


def choice_ids(src):
    """The item ids on a page, in review.js's order (h2 items s1, s2, ... then [data-review-question])."""
    m = re.search(r"<body[^>]*>", src)
    body = m.group(0) if m else ""
    inner = re.sub(r"<script.*?</script>", "", src[m.end():] if m else src, flags=re.S)
    ids = [] if 'data-review-h2="off"' in body else [f"s{i}" for i, _ in enumerate(re.findall(r"<h2(?:\s[^>]*)?>", inner), 1)]
    return ids + [html.unescape(q) for q in re.findall(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*\bdata-review-question="([^"]*)"', inner)]


def _nat(text):
    """Natural sort key: "2" before "10", case ignored."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", text.lower()) if t]


def _series(p):
    """(series, number) for a numbered page: a title that starts with a number ("2. Sign in") is in the
    "" series; otherwise the first number in the page key ("design-review-2-..." is series
    "design-review-", number 2). Unnumbered pages are their own series with no number."""
    m = re.match(r"\s*(\d+)\b", p["title"])
    if m:
        return "", int(m.group(1))
    m = re.match(r"(\D*?)(\d+)", p["key"])
    if m:
        return m.group(1).lower(), int(m.group(2))
    return "\0" + p["key"], None


def order_pages(pages, manifest):
    """Index card order, never by change time: priority (lower first), then the unified review/ page,
    then by series. A series sits where its first page sits in the folder's _status.json (manifest:
    its keys in file order); inside one, pages run by their number naturally (2 before 10), then by
    manifest position, then by title. Pages not in the manifest come after those that are."""
    pos = {k: i for i, k in enumerate(manifest)}
    far = len(manifest)
    first = {}
    for p in pages:
        ser = _series(p)[0]
        first[ser] = min(first.get(ser, far), pos.get(p["key"], far))
    def key(p):
        ser, num = _series(p)
        return (p.get("priority", 50), p["key"] != "review/", first[ser], _nat(ser),
                num if num is not None else -1, pos.get(p["key"], far), _nat(p["title"]), p["key"])
    return sorted(pages, key=key)


def card(pg, show_folder=False, compact=False):
    """One page card: chips, title and note on the left; the open count (or a choices page's
    per-choice counts), when it changed and Stale on the right. compact: the Reference grid and
    Completed list, title and "Folder · note" only."""
    sig = f'{pg["state"]}|{int(pg["mtime"])}|{pg["note"]}|{",".join(pg["chips"])}|{pg["open"]}|{pg.get("tally")}'
    chips = "".join(f'<span class="chip {CHIP_CLASS.get(c, "c-custom")}">{esc(c)}</span>' for c in pg["chips"])
    cls = {"needs-you": "needs", "done": "done"}.get(pg["state"], "")
    attrs = (f'data-key="{esc(pg["folder"] + "/" + pg["key"])}" data-sig="{esc(sig)}" '
             f'data-mtime="{int(pg["mtime"])}" data-first="{int(pg["first"])}"'
             + (f' data-project="{esc(pg["folder"])}"' if show_folder else ""))
    title = f'<p class="t"><a href="{esc(pg["href"])}">{esc(pg["title"])}</a></p>'
    if compact:
        note = " · ".join(x for x in [esc(FOLDERS[pg["folder"]]) if show_folder else "", esc(pg["note"])] if x)
        return (f'<li class="card compact {cls}" {attrs}>{title}' + (f'<p class="n">{note}</p>' if note else "")
                + f'<div class="chips">{chips}</div></li>')
    if pg.get("tally"):
        count = f'<span class="tally">{esc(pg["tally"])}</span>'
    elif pg["open"] is not None:
        count = f'<span class="opn{" zero" if not pg["open"] else ""}">{pg["open"]} open</span>'
    else:
        count = ""
    where = f'<span>{esc(FOLDERS[pg["folder"]])}</span>' if show_folder else ""
    ago = f'<span class="ago" data-ts="{int(pg["mtime"])}" title="Changed {esc(when(pg["mtime"]))}">Changed {esc(when(pg["mtime"]))}</span>'
    return (f'<li class="card {cls}" {attrs}><div class="cmain"><div class="chips">{chips}</div>{title}'
            + (f'<p class="n">{esc(pg["note"])}</p>' if pg["note"] else "")
            + f'<p class="m">{where}<code>{esc(pg["key"])}</code></p></div>'
            f'<div class="cside">{count}{ago}{stale_btn(pg)}</div></li>')


def stale_btn(pg):
    if pg["state"] != "needs-you" or pg["key"] == "review/" or f'{pg["folder"]}/{pg["key"]}' in PROTECTED:
        return ""
    return (f'<button type="button" class="stale-btn" data-stale-folder="{esc(pg["folder"])}" data-stale-page="{esc(pg["key"])}" '
            f'data-stale-title="{esc(pg["title"])}">Stale: remove this page</button>')


def section(sid, label, pages, show_folder=False):
    """Needs you as full cards, Reference as a grid, Completed folded (a compact list)."""
    compact = sid != "needs-you"
    ul = "cards grid" if sid == "reference" else "cards compact-list" if sid == "done" else "cards"
    body = (f'<ul class="{ul}">{"".join(card(p, show_folder, compact) for p in pages)}</ul>' if pages
            else '<p class="empty">Nothing here.</p>')
    if sid == "done":
        return (f'<section class="sect"><details data-sect="{sid}"><summary><span>{label}</span> '
                f'<span class="count">{len(pages)}</span></summary>{body}</details></section>')
    extra = ""
    if sid == "needs-you":
        opens = sum(p["open"] or 0 for p in pages if p["key"] != "review/")
        if opens:
            extra = f' <span class="pill amber">{opens} open item{"" if opens == 1 else "s"}</span>'
    return (f'<section class="sect" data-sect="{sid}"><h2>{label} <span class="count">{len(pages)}</span>{extra}</h2>'
            f'{body}</section>')


ICON = ('<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true"><rect x="3" y="5" width="22" height="18" rx="4" '
        'fill="none" stroke="currentColor" stroke-width="2"></rect><path d="M8 12l4 4 8-8" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></path></svg>')


def shell(title, sub, live, extra="", crumb="", root=False):
    """The white header (crumb, title, subtitle; on the root the icon, review windows and the
    Projects filter on the right), then the live-updating content."""
    side = ""
    if root:
        wins = "".join(f'<span class="mono-pill">{esc(w)} {esc(TZ_LABEL)}</span>' for w in CONFIG.get("review_windows", []))
        side = ('<div class="hside">' + (f'<span class="lbl">Review windows</span>{wins}' if wins else "") + f'{extra}</div>')
    head = ('<div class="hrow"><div class="hmain">'
            + (f"<a class=crumb href='{crumb[0]}'>&larr; {esc(crumb[1])}</a>" if crumb else "")
            + f'<div class="htitle">{ICON if root else ""}<h1>{esc(title)}</h1></div>'
            + (f'<p>{sub}</p>' if sub else "") + f'</div>{side}</div>')
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><link rel=stylesheet href='{asset('site.css')}'><script src='{asset('theme.js')}'></script></head>"
            f"<body class=site><header class=top><div class=wrap>{head}</div></header>"
            f"<main class=wrap id=live>{live}</main>"
            f"<script src='{asset('live.js')}'></script>" + (f"<script src='{asset('filter.js')}'></script>" if extra else "") + "</body></html>\n")


def page_key(k):
    """Port of review.js's pageKey() (see _site/serve.py, which must match it too): the name a
    page's answers, and now its round history, are stored under."""
    s = re.sub(r"[^a-z0-9._-]+", "-", k.lower())
    s = re.sub(r"^[-.]+|-+$", "", s)
    if len(s) > 120:
        digits, h = "0123456789abcdefghijklmnopqrstuvwxyz", 0
        for c in k:
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        n, out = h, []
        while n:
            n, r = divmod(n, 36)
            out.append(digits[r])
        s = s[:111] + "-" + ("".join(reversed(out)) or "0")
    return s or "page"


def history_rounds(folder, key):
    """Every archived round for one page, newest first (see _saved/history/<page-key>/ in serve.py)."""
    name = page_key(CONFIG.get("key_prefix", "review:") + f"/{folder}/{key}")
    hdir = os.path.join(ROOT, "_saved", "history", name)
    rounds = []
    if os.path.isdir(hdir):
        for fn in sorted(os.listdir(hdir)):
            if not fn.endswith(".json"):
                continue
            try:
                rounds.append(json.load(open(os.path.join(hdir, fn))))
            except (OSError, ValueError):
                continue
    rounds.sort(key=lambda e: e.get("round", 0), reverse=True)
    return rounds


def page_choices(src):
    """The page's own answer choices from its <body> (data-review-options, data-review-default), the rule
    serve.py's round text uses: ([(value, label), ...], default value or ""), or None for Yes / No / Changes."""
    m = re.search(r"<body[^>]*>", src)
    get = lambda n: html.unescape((re.search(n + r'="([^"]*)"', m.group(0) if m else "") or [None, ""])[1])
    opts = [(v.strip(), lab.strip()) for v, _, lab in (p.partition(":") for p in get("data-review-options").split(","))
            if v.strip() and lab.strip()]
    if not opts:
        return None
    d = get("data-review-default")
    return opts, d if any(v == d for v, _ in opts) else ""


def round_count_line(answers, choices=None, n_items=0):
    """A round's count line: "x of y Yes", or on a choices page the per-choice counts ("1 start · 2 hold"), where each of
    the page's n_items choice items with no saved choice counts as the default."""
    counted = [k for k, v in (answers or {}).items() if isinstance(v, dict) and not k.startswith(("_", "import:")) and not v.get("locked")]
    if choices:
        opts, default = choices
        labels = dict(opts)
        tally = {lab.lower(): 0 for _, lab in opts}
        picked = [answers[k]["v"] for k in counted if answers[k].get("v") in labels]
        for v in picked:
            tally[labels[v].lower()] += 1
        if default:
            tally[labels[default].lower()] += max(n_items - len(picked), 0)
        return " · ".join(f"{n} {k}" for k, n in tally.items())
    yes = sum(1 for k in counted if answers[k].get("v") == "yes")
    return f"{yes} of {len(counted)} Yes" if counted else "no items"


def page_file_rounds(folder, key):
    """A page file's closed rounds, newest first, in the shape history_page() shows: round, build, dates, the
    count line and the round's Copy results text."""
    try:
        doc = pagefile.load(os.path.join(ROOT, folder, key + ".json"))
    except (OSError, ValueError):
        return []
    kind_type = {"review": "section", "checklist": "check", "journey": "step", "backlog": "choice",
                 "questions": "question", "reference": "info", "status": "info"}[doc["kind"]]
    types = {it["id"]: it.get("type", kind_type) for it in doc["items"]}
    yn = [i for i, t in types.items() if t not in ("question", "choice", "info")]
    choice = [i for i, t in types.items() if t == "choice"]
    out = []
    for r in reversed([r for r in doc["rounds"] if r.get("closed")]):
        a = r.get("answers", {})
        if choice and not yn:
            opts = doc["options"]
            labels = {c["value"]: c["label"].lower() for c in opts["choices"]}
            tally = {lab: 0 for lab in labels.values()}
            for i in choice:
                v = (a.get(i) or {}).get("answer") or opts.get("default", "")
                if v in labels:
                    tally[labels[v]] += 1
            count = " · ".join(f"{n} {k}" for k, n in tally.items())
        else:
            count = f'{sum(1 for i in yn if (a.get(i) or {}).get("answer") == "yes")} of {len(yn)} Yes' if yn else "no items"
        out.append({"round": r["round"], "build": r.get("build") or "", "opened": r.get("opened"), "closed": r.get("closed"),
                    "count": count, "results_text": r.get("results", "")})
    return out


def history_html(folder, pages):
    """<folder>/history/: every page's rounds, each page collapsed, newest round first."""
    groups = []
    for p in pages:
        if p["key"] == "history/":
            continue
        if p.get("kind"):
            rounds = page_file_rounds(folder, p["key"])
            if not rounds:
                continue
            items = [f'<details class="rvhist-round"><summary>Round {esc(str(e["round"]))}'
                     + (f' &middot; build {esc(e["build"])}' if e["build"] else "")
                     + f' &middot; {esc((e["opened"] or "")[:10])} to {esc((e["closed"] or "")[:10])} &middot; {esc(e["count"])}'
                     + f'</summary><pre class="hist-text">{esc(e["results_text"])}</pre></details>' for e in rounds]
            n = len(rounds)
            groups.append(f'<details class="rvhist"><summary>{esc(p["title"])} ({n} round{"" if n == 1 else "s"})</summary>'
                          f'<p class="m"><a href="{esc(p["href"])}">Full page</a></p>{"".join(items)}</details>')
            continue
        rounds = history_rounds(folder, p["key"])
        if not rounds:
            continue
        src = read(target(folder, p["key"]))
        choices = page_choices(src)
        info = review_info(src) if choices else None
        n_choice = info[3] if info else 0
        items = []
        for e in rounds:
            summary = (f'Round {esc(str(e.get("round", "")))}'
                       + (f' &middot; build {esc(e.get("build", ""))}' if e.get("build") else "")
                       + f' &middot; {esc((e.get("opened") or "")[:10])} to {esc((e.get("closed") or "")[:10])}'
                       + f' &middot; {esc(round_count_line(e.get("answers"), choices, n_choice))}')
            items.append(f'<details class="rvhist-round"><summary>{summary}</summary>'
                         f'<pre class="hist-text">{esc(e.get("results_text", ""))}</pre></details>')
        n = len(rounds)
        groups.append(f'<details class="rvhist"><summary>{esc(p["title"])} ({n} round{"" if n == 1 else "s"})</summary>'
                      f'<p class="m"><a href="{esc(p["href"])}">Full page</a></p>{"".join(items)}</details>')
    body = "".join(groups) or '<p class="empty">No rounds yet.</p>'
    return shell(f"{FOLDERS[folder]}: history", "Past review and sign-off rounds.", body, crumb=(f"/{folder}/", FOLDERS[folder]))


def history_page(folder, pages):
    """Write <folder>/history/index.html."""
    hdir = os.path.join(ROOT, folder, "history")
    os.makedirs(hdir, exist_ok=True)
    with open(os.path.join(hdir, "index.html"), "w") as f:
        f.write(history_html(folder, pages))


def ensure_reference_entry(folder, key, note):
    """Seed a manifest entry that must never default to needs-you (gen-index.py's own pages). Runs before
    collect(), which would otherwise record the page as unclassified; an entry with no state gets one,
    and a state already set is left alone."""
    mpath = os.path.join(ROOT, folder, "_status.json")
    try:
        manifest = json.load(open(mpath))
    except (OSError, ValueError):
        manifest = {}
    ent = manifest.setdefault(key, {})
    if "state" not in ent:
        ent["state"] = "reference"
        ent.setdefault("note", note)
        os.makedirs(os.path.dirname(mpath), exist_ok=True)
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")


def folder_html(d, pages):
    """One folder's index: Needs you, Reference, then Completed folded."""
    by = {s: [p for p in pages if p["state"] == s] for s, _ in SECTIONS}
    summary = (f'<p class="muted">{len(by["needs-you"])} need you &middot; {len(by["reference"])} reference '
               f'&middot; {len(by["done"])} completed</p>')
    live = summary + "".join(section(s, label, by[s]) for s, label in SECTIONS)
    return shell(FOLDERS[d], esc(BLURB[d]), live, crumb=("/", f'{CONFIG.get("title", "Pages")} hand-off · all folders'))


def main():
    everything = {}
    for d in FOLDERS:
        has_html = any(k != "history/" for k in discover(d)) if os.path.isdir(os.path.join(ROOT, d)) else False
        if has_html or os.path.exists(os.path.join(ROOT, d, "_status.json")):
            ensure_reference_entry(d, "history/", HISTORY_NOTE)
        if not os.path.exists(os.path.join(ROOT, d, "history", "index.html")):
            # A first version for collect() to find, so the folder's index lists it from the first run.
            history_page(d, [])
        pages = collect(d)
        everything[d] = pages
        history_page(d, pages)
        with open(os.path.join(ROOT, d, "index.html"), "w") as f:
            f.write(folder_html(d, pages))
    with open(os.path.join(ROOT, "index.html"), "w") as f:
        f.write(root_html(everything))
    print(" ".join(f"{d}={sum(p['state'] == 'needs-you' for p in everything[d])}" for d in FOLDERS))


def root_html(everything):
    """The root index: Needs you now by folder, Reference, Completed and the folder cards."""
    cfg = {}
    try:
        cfg = json.load(open(os.path.join(ROOT, "_site", "focus.json")))
    except (OSError, ValueError):
        pass
    cfg.setdefault("order", CONFIG.get("order", []))
    order = [d for d in cfg.get("order", []) if d in FOLDERS] + [d for d in FOLDERS if d not in cfg.get("order", [])]

    groups = []
    counts = {}
    for d in order:
        now_d = [p for p in everything[d] if p["state"] == "needs-you"]
        counts[d] = len(now_d)
        if not now_d:
            continue
        # The unified review page repeats its source pages' items, so its own count would add them twice.
        opens = sum(p["open"] or 0 for p in now_d if p["key"] != "review/")
        picks = sum(1 for p in now_d if p.get("tally"))
        parts = ([f"{opens} open"] if opens else []) + ([f"{picks} to pick"] if picks else [])
        parts = parts or [f'{len(now_d)} page{"" if len(now_d) == 1 else "s"}']
        label = (f'<span class="gname"><a href="/{d}/">{esc(FOLDERS[d])}</a></span><span>{" · ".join(parts)}</span>'
                 f'<span class="rule"></span>')
        groups.append(f'<section class="sect grp" data-project="{d}" data-sect="now-{d}" data-open="{opens}">'
                      f'<div class="ghead">{label}</div>'
                      f'<ul class="cards">{"".join(card(p) for p in now_d)}</ul></section>')
    total = sum(counts.values())
    folders = "".join(
        f'<li class="card{" needs" if n else ""}" data-project="{d}" data-key="folder/{d}" data-sig="{n}|{len(everything[d])}" '
        f'data-mtime="{int(max([p["mtime"] for p in everything[d]] or [0]))}" data-first="0">'
        f'<p class="t"><a href="/{d}/">{esc(FOLDERS[d])}</a></p><p class="n">{esc(BLURB[d])}</p>'
        f'<p class="big{"" if n else " zero"}">{n}</p><p class="m"><span>need you</span><a href="/{d}/history/">History</a></p>'
        f'<div class="chips"></div></li>'
        for d in order for n in [counts[d]])
    open_total = sum(p["open"] or 0 for d in order for p in everything[d] if p["state"] == "needs-you" and p["key"] != "review/")
    refs = [p for d in order for p in everything[d] if p["state"] == "reference"]
    done = [p for d in order for p in everything[d] if p["state"] == "done"]
    ref_body = (f'<ul class="cards grid">{"".join(card(p, True, True) for p in refs)}</ul>' if refs else '<p class="empty">Nothing here.</p>')
    done_body = (f'<ul class="cards compact-list">{"".join(card(p, True, True) for p in done)}</ul>' if done else '<p class="empty">Nothing here.</p>')
    live = (f'<section class="sect" data-sect="now"><h2>Needs you now <span class="count"><span id="now-count">{total}</span> pages</span>'
            f'<span class="pill amber" id="now-open-pill"{"" if open_total else " hidden"}><span id="now-open">{open_total}</span> open items</span></h2>'
            f'<p class="empty" id="now-empty"{" hidden" if total else ""}>Nothing needs you in the projects you picked.</p>'
            + "".join(groups) + '</section>'
            + f'<section class="sect" data-sect="reference"><h2>Reference <span class="count">{len(refs)}</span></h2>{ref_body}</section>'
            + f'<section class="sect"><details data-sect="done"><summary><span>Completed</span> <span class="count">{len(done)}</span></summary>{done_body}</details></section>'
            + f'<section class="sect" data-sect="folders"><h2>Folders</h2><ul class="folders">{folders}</ul></section>')
    chips = "".join(f'<label class="fopt"><input type="checkbox" value="{d}" checked> <span class="fl">{esc(FOLDERS[d])}</span>'
                    f' <span class="count" data-count="{d}">{counts[d]}</span></label>' for d in order)
    filt = ('<div class="filter" id="filter"><button type="button" class="fbtn" aria-haspopup="true" aria-expanded="false" '
            'aria-controls="filter-menu">Projects: All <span aria-hidden="true">&#9662;</span></button>'
            f'<div class="fmenu" id="filter-menu" role="group" aria-label="Projects" hidden>{chips}'
            '<div class="fact"><button type="button" data-all>All</button><button type="button" data-none>None</button></div></div></div>')
    return shell(CONFIG.get("title", "Pages") + " hand-off", CONFIG.get("subtitle", ""), live, filt, root=True)


if __name__ == "__main__":
    main()

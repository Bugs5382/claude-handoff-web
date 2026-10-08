#!/usr/bin/env python3
"""Rebuild index.html for the web root and each folder from <folder>/_status.json.

Each manifest maps a page path (relative to its folder: "x.html", "dir/", "dir/y.html") to
{"state": "needs-you"|"reference"|"done", "note": "...", "chips": ["Decision needed"]}.
"first_seen" is added automatically the first time a page is met. Pages that exist but are not in
the manifest show under "Needs you" with a "Not classified" chip, so nothing hides silently.
Names, folders, blurbs and the timezone come from site.json next to this script. See _site/README.md.
"""
import datetime as dt
import html
import json
import os
import re
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
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
    """Count review.js items on a page: (items, open, reopened). None if the page has no review.js."""
    if "review.js" not in src:
        return None
    m = re.search(r"<body[^>]*>", src)
    body = m.group(0) if m else ""
    get = lambda n: html.unescape((re.search(n + r'="([^"]*)"', body) or [None, ""])[1])
    reopen = {p.split("=", 1)[0].strip() for p in get("data-review-reopen").split("|") if "=" in p}
    approved = {a.strip() for a in get("data-review-approved").split(",") if a.strip()} - reopen
    if get("data-review-controls") == "off":
        return None
    inner = re.sub(r"<script.*?</script>", "", src[m.end():] if m else src, flags=re.S)
    h2 = 0 if get("data-review-h2") == "off" else len(re.findall(r"<h2[\s>]", inner))
    n = h2 + len(re.findall(r'data-review-question="', inner))
    return n, max(n - len(approved), 0), len(reopen)


def when(ts):
    d = dt.datetime.fromtimestamp(ts, ET)
    return d.strftime("%b %-d, %-I:%M %p ") + TZ_LABEL


def discover(folder):
    fp = os.path.join(ROOT, folder)
    keys = []
    for e in sorted(os.listdir(fp)):
        if e.startswith(("_", ".")) or e == "index.html":
            continue
        full = os.path.join(fp, e)
        if os.path.isdir(full):
            keys.append(e + "/")
        elif e.endswith(".html"):
            keys.append(e)
    return keys


def collect(folder):
    fp = os.path.join(ROOT, folder)
    os.makedirs(fp, exist_ok=True)
    mpath = os.path.join(fp, "_status.json")
    manifest = json.load(open(mpath)) if os.path.exists(mpath) else {}
    keys = discover(folder) + [k for k in manifest if k not in discover(folder) and os.path.exists(target(folder, k))]
    dirty, pages = False, []
    for k in keys:
        p = target(folder, k)
        mt = mtime(p)
        ent = manifest.get(k)
        known = ent is not None
        if not known:
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
        open_items = info[1] if info and state == "needs-you" else None
        if info and state == "needs-you":
            n, open_n, reo = info
            if reo:
                chips.append("Reopened")
            if open_n and "To review" not in chips:
                chips.append("To review")
            if n and not open_n:
                chips.append("Approved")
        chips.append({"reference": "Reference", "done": "Done"}.get(state, ""))
        chips += [c for c in ent.get("chips", []) if c]
        chips = [c for i, c in enumerate(chips) if c and c not in chips[:i]]
        first = dt.datetime.fromisoformat(ent["first_seen"]).timestamp()
        pages.append(dict(folder=folder, key=k, href=f"/{folder}/{k}", title=title_of(src, k), note=ent.get("note", ""),
                          state=state, chips=chips, mtime=mt, first=first, open=open_items, priority=ent.get("priority", 50)))
    if dirty:
        with open(mpath, "w") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.write("\n")
    pages.sort(key=lambda x: -x["mtime"])
    return pages


def card(pg, show_folder=False):
    sig = f'{pg["state"]}|{int(pg["mtime"])}|{pg["note"]}|{",".join(pg["chips"])}|{pg["open"]}'
    chips = "".join(f'<span class="chip {CHIP_CLASS.get(c, "c-custom")}">{esc(c)}</span>' for c in pg["chips"])
    where = f'<span>{esc(FOLDERS[pg["folder"]])}</span>' if show_folder else ""
    cls = {"needs-you": "needs", "done": "done"}.get(pg["state"], "")
    return (f'<li class="card {cls}" data-key="{esc(pg["folder"] + "/" + pg["key"])}" data-sig="{esc(sig)}" '
            f'data-mtime="{int(pg["mtime"])}" data-first="{int(pg["first"])}">'
            f'<p class="t"><a href="{esc(pg["href"])}">{esc(pg["title"])}</a></p>'
            + (f'<p class="n">{esc(pg["note"])}</p>' if pg["note"] else "")
            + f'<div class="chips">{chips}</div>'
            f'<p class="m">{where}' + (f'<span><b>{pg["open"]} open item{"" if pg["open"] == 1 else "s"}</b></span>' if pg["open"] is not None else "") + f'<span>Changed {when(pg["mtime"])}</span><code>{esc(pg["key"])}</code></p>'
            + stale_btn(pg) + '</li>')


def stale_btn(pg):
    if pg["state"] != "needs-you" or pg["key"] == "review/" or f'{pg["folder"]}/{pg["key"]}' in PROTECTED:
        return ""
    return (f'<button type="button" class="stale-btn" data-stale-folder="{esc(pg["folder"])}" data-stale-page="{esc(pg["key"])}" '
            f'data-stale-title="{esc(pg["title"])}">Stale: remove this page</button>')


def section(sid, label, pages, show_folder=False):
    body = (f'<ul class="cards">{"".join(card(p, show_folder) for p in pages)}</ul>' if pages
            else '<p class="empty">Nothing here.</p>')
    if sid == "done":
        return (f'<section class="sect"><details data-sect="{sid}"><summary>{label} ({len(pages)})</summary>'
                f'{body}</details></section>')
    return (f'<section class="sect" data-sect="{sid}"><h2>{label} <span class="count">{len(pages)}</span></h2>'
            f'{body}</section>')


def shell(title, sub, live, extra=""):
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><link rel=stylesheet href='{asset('site.css')}'></head>"
            f"<body class=site><header class=top><div class=wrap><h1>{esc(title)}</h1><p>{sub}</p>{extra}</div></header>"
            f"<main class=wrap id=live>{live}</main>"
            f"<script src='{asset('live.js')}'></script>" + (f"<script src='{asset('filter.js')}'></script>" if extra else "") + "</body></html>\n")


def main():
    everything = {}
    for d, name in FOLDERS.items():
        pages = collect(d)
        everything[d] = pages
        by = {s: [p for p in pages if p["state"] == s] for s, _ in SECTIONS}
        summary = (f'<p class="muted">{len(by["needs-you"])} need you &middot; {len(by["reference"])} reference '
                   f'&middot; {len(by["done"])} completed</p>')
        live = summary + "".join(section(s, label, by[s]) for s, label in SECTIONS)
        with open(os.path.join(ROOT, d, "index.html"), "w") as f:
            f.write(shell(name, f"<a href='/'>All folders</a> &middot; {esc(BLURB[d])}", live))
    cfg = {}
    try:
        cfg = json.load(open(os.path.join(ROOT, "_site", "focus.json")))
    except (OSError, ValueError):
        pass
    cfg.setdefault("order", CONFIG.get("order", []))
    order = [d for d in cfg.get("order", []) if d in FOLDERS] + [d for d in FOLDERS if d not in cfg.get("order", [])]

    def rank(p):
        return (p.get("priority", 50), p["key"] != "review/", -p["mtime"])
    groups = []
    counts = {}
    for d in order:
        now_d = sorted((p for p in everything[d] if p["state"] == "needs-you"), key=rank)
        counts[d] = len(now_d)
        if not now_d:
            continue
        opens = sum(p["open"] or 0 for p in now_d)
        label = (f'{esc(FOLDERS[d])} <span class="count">{len(now_d)}</span>'
                 + (f' <span class="muted">{opens} open items</span>' if opens else ""))
        groups.append(f'<section class="sect" data-project="{d}" data-sect="now-{d}"><h2>{label}</h2>'
                      f'<ul class="cards">{"".join(card(p) for p in now_d)}</ul></section>')
    total = sum(counts.values())
    folders = "".join(
        f'<li class="card{" needs" if n else ""}" data-project="{d}" data-key="folder/{d}" data-sig="{n}|{len(everything[d])}" '
        f'data-mtime="{int(max([p["mtime"] for p in everything[d]] or [0]))}" data-first="0">'
        f'<p class="t"><a href="/{d}/">{esc(FOLDERS[d])}</a></p><p class="n">{esc(BLURB[d])}</p>'
        f'<p class="big{"" if n else " zero"}">{n}</p><p class="m"><span>need you</span></p>'
        f'<div class="chips"></div></li>'
        for d in order for n in [counts[d]])
    live = (f'<section class="sect" data-sect="now"><h2>Needs you now <span class="count" id="now-count">{total}</span></h2>'
            f'<p class="empty" id="now-empty" hidden>Nothing needs you in the projects you picked.</p></section>'
            + "".join(groups)
            + f'<section class="sect" data-sect="folders"><h2>Folders</h2><ul class="folders">{folders}</ul></section>')
    chips = "".join(f'<label class="fopt"><input type="checkbox" value="{d}" checked> <span class="fl">{esc(FOLDERS[d])}</span>'
                    f' <span class="count" data-count="{d}">{counts[d]}</span></label>' for d in order)
    filt = ('<div class="filter" id="filter"><button type="button" class="fbtn" aria-haspopup="true" aria-expanded="false" '
            'aria-controls="filter-menu">Projects: All <span aria-hidden="true">&#9662;</span></button>'
            f'<div class="fmenu" id="filter-menu" role="group" aria-label="Projects" hidden>{chips}'
            '<div class="fact"><button type="button" data-all>All</button><button type="button" data-none>None</button></div></div></div>')
    with open(os.path.join(ROOT, "index.html"), "w") as f:
        f.write(shell(CONFIG.get("title", "Pages"), CONFIG.get("subtitle", ""), live, filt))
    print(" ".join(f"{d}={sum(p['state'] == 'needs-you' for p in everything[d])}" for d in FOLDERS))


if __name__ == "__main__":
    main()

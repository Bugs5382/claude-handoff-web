#!/usr/bin/env python3
"""Build /<folder>/review/index.html: one page holding every item of the folder's needs-you pages
(from <folder>/_status.json), grouped by source page. Each group is collapsed (one open at a time) and
its heading shows the page title, a one-line summary, the open count, its chips and a Stale button.
Each item shows its question and answer controls first; bulky content sits behind "Show details" in an
iframe with its page's CSS. Items come from [data-review-question] sections, or from <h2> sections on plain pages.
Approved, reopened and reset attributes on the source pages carry through, prefixed by page.

Usage: build-review.py <folder>    (rerun after any source page or manifest change)
"""
import datetime as dt
import html
import json
import pathlib
import re
import sys

WEB = pathlib.Path(__file__).resolve().parent.parent
try:
    SITE = json.loads((WEB / "site.json").read_text())
except (OSError, ValueError):
    SITE = {}
try:
    NAMES = {f["id"]: f["name"] for f in json.loads((WEB / "site.json").read_text())["folders"]}
except (OSError, ValueError, KeyError):
    NAMES = {}


def attr(tag, name):
    m = re.search(r"\s" + name + r'="([^"]*)"', tag)
    return html.unescape(m.group(1)) if m else ""


def sections(inner):
    """Yield (open_tag, outer_html) for each top-level <section data-review-question=...>."""
    for m in re.finditer(r"<section\b[^>]*\bdata-review-question=\"[^\"]*\"[^>]*>", inner):
        depth, pos = 1, m.end()
        for t in re.finditer(r"<(/?)section\b[^>]*>", inner[pos:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                yield m.group(0), inner[m.start():pos + t.end()]
                break


def load(prefix, path):
    src = path.read_text(errors="ignore")
    body = re.search(r"<body[^>]*>", src).group(0)
    head = src[:src.index(body)]
    styles = "".join(re.findall(r"<style[^>]*>.*?</style>", head, re.S))
    styles += "".join(l for l in re.findall(r"<link[^>]*rel=.?stylesheet[^>]*>", head) if "/_site/" not in l)
    title = re.search(r"<title>(.*?)</title>", src, re.S)
    title = html.unescape(title.group(1).strip()) if title else path.name
    inner = src[src.index(body) + len(body):].split("</body>")[0]
    inner = re.sub(r"<script\b.*?</script>", "", inner, flags=re.S)
    approved = {s.strip() for s in attr(body, "data-review-approved").split(",") if s.strip()}
    reopen = dict(p.split("=", 1) for p in attr(body, "data-review-reopen").split("|") if "=" in p)
    reopen = {k.strip(): v.strip() for k, v in reopen.items()}
    items = []
    found = list(sections(inner))
    if found:
        for tag, chunk in found:
            sid, t = attr(tag, "data-review-question"), attr(tag, "data-title")
            items.append((sid, t, chunk))
    elif attr(body, "data-review-h2") != "off":
        for i, ch in enumerate([c for c in re.split(r"(?=<h2[\s>])", inner) if c.startswith("<h2")], 1):
            t = re.sub(r"<[^>]+>", "", re.match(r"<h2[^>]*>(.*?)</h2>", ch, re.S).group(1)).strip()
            items.append((f"s{i}", html.unescape(t), ch))
    out = [dict(id=f"{prefix}.{sid}", title=t, html=ch, approved=sid in approved and sid not in reopen,
                reopen=reopen.get(sid, "")) for sid, t, ch in items]
    reset = attr(body, "data-review-reset")
    ver, _, ids = reset.partition(":")
    rids = [i.strip() for i in ids.split(",") if i.strip()] + [k for k in reopen if k not in ids.split(",")]
    tagged = f"{prefix}@{ver}:" + ",".join(f"{prefix}.{i}" for i in rids) if ver else ""
    extra = {"skip": attr(body, "data-review-skip") == "on", "import": attr(body, "data-review-import"),
             "build": attr(body, "data-build")}
    return title, styles, out, tagged, extra


def frame(styles, chunk, base):
    doc = (f'<!doctype html><html><head><meta charset="utf-8"><base href="{base}" target="_blank">'
           f'{styles}<style>body{{margin:0;padding:6px 10px;max-width:none}} section{{display:block !important}}</style></head>'
           f'<body>{chunk}</body></html>')
    return ('<iframe class="shot" loading="lazy" title="Details" srcdoc="' + html.escape(doc, quote=True) +
            '" onload="window.rvFit&&rvFit(this)"></iframe>')


CHROME = re.compile(r"<(header|nav|footer)\b.*?</\1>", re.S | re.I)
BULKY = re.compile(r"<(img|svg|pre|table|iframe|video|canvas|figure|style|template)\b", re.I)


def text_of(chunk):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", chunk))).strip()


def clean(chunk, title):
    """Drop page chrome (header/nav/footer) and the item's own heading, which the group already shows."""
    chunk = CHROME.sub("", chunk)
    m = re.match(r"\s*<section\b[^>]*>", chunk)
    if m:
        chunk = chunk[m.end():]
        chunk = chunk[:chunk.rfind("</section>")] if "</section>" in chunk else chunk
    h = re.search(r"<(h[1-4])\b[^>]*>(.*?)</\1>", chunk, re.S)
    if h and (chunk[:h.start()].strip() == "" or text_of(h.group(2)) == title.strip()):
        chunk = chunk[:h.start()] + chunk[h.end():]
    return chunk.replace("data-review-question=", "data-was-question=")


def summary_of(src, note):
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', src, re.I)
    if m and m.group(1).strip():
        line = html.unescape(m.group(1))
    else:
        body = src[src.find("<body"):]
        m = re.search(r"<h1\b.*?</h1>\s*(?:</?\w+[^>]*>\s*)*?<p\b[^>]*>(.*?)</p>", body, re.S) or re.search(r"<p\b[^>]*>(.*?)</p>", body, re.S)
        line = text_of(m.group(1)) if m else ""
        if len(line) < 25:
            line = note
    return line if len(line) <= 160 else line[:157].rsplit(" ", 1)[0] + "..."


def stale_log(folder, days=7):
    """Pages marked stale in this folder in the last `days` (for Copy results)."""
    out, cutoff = [], dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    try:
        for line in (WEB / "_saved" / "stale-log.json").read_text().splitlines():
            try:
                e = json.loads(line)
                if e.get("folder") == folder and dt.datetime.fromisoformat(e["at"]) >= cutoff:
                    out.append(e["page"])
            except (ValueError, KeyError):
                continue
    except OSError:
        pass
    return list(dict.fromkeys(out))


def chip(label, cls="c-custom"):
    return f'<span class="chip {cls}">{html.escape(label)}</span>'


def main(folder):
    fdir = WEB / folder
    manifest = json.loads((fdir / "_status.json").read_text())
    protected = set(SITE.get("protected", []))
    srcs = [k for k, v in manifest.items() if v.get("state") == "needs-you" and k != "review/"]
    groups, approved, reopen, resets, open_n, skip, imports = [], [], [], [], 0, False, []
    for key in srcs:
        path = fdir / (key + "index.html" if key.endswith("/") else key)
        if not path.exists():
            continue
        prefix = re.sub(r"[^a-z0-9]+", "-", key.lower().removesuffix(".html").removesuffix("/index").rstrip("/")).strip("-")
        title, styles, items, tagged, extra = load(prefix, path)
        if not items:
            continue
        skip = skip or extra["skip"]
        if extra["import"]:
            k, _, pre = extra["import"].partition("|")
            imports.append(f"{k}|{prefix}.{pre}")
        if tagged:
            resets.append(tagged)
        base = f"/{folder}/" + (key if key.endswith("/") else (key.rsplit("/", 1)[0] + "/" if "/" in key else ""))
        n_open = sum(not i["approved"] for i in items)
        n_reo = sum(bool(i["reopen"]) for i in items)
        chips = chip(f"{n_open} open", "c-review" if n_open else "c-approved")
        chips += chip("Reopened", "c-reopened") if n_reo else ""
        chips += chip(f"{len(items) - n_open} approved", "c-approved") if len(items) - n_open and n_open else ""
        chips += "".join(chip(c) for c in manifest[key].get("chips", []) if c)
        stale = "" if f"{folder}/{key}" in protected else (
            f'<button type="button" class="stale-btn" data-stale-folder="{html.escape(folder, quote=True)}" '
            f'data-stale-page="{html.escape(key, quote=True)}" data-stale-title="{html.escape(title, quote=True)}">Stale: remove this page</button>')
        body = []
        for it in items:
            if it["approved"]:
                approved.append(it["id"])
            else:
                open_n += 1
            if it["reopen"]:
                reopen.append(f'{it["id"]}={it["reopen"]}')
            chunk = clean(it["html"], it["title"])
            small = len(text_of(chunk)) <= 400 and not BULKY.search(chunk)
            detail = (f'<div class="lead">{chunk}</div>' if small and text_of(chunk) else "") if small else \
                f'<details class="rv-details"><summary>Show details</summary>{frame(styles, chunk, base)}</details>'
            body.append(f'<div class="item" data-review-question="{html.escape(it["id"], quote=True)}" '
                        f'data-title="{html.escape(title + ": " + it["title"], quote=True)}">'
                        f'<div class="ih">{html.escape(it["title"])} <code>{html.escape(it["id"])}</code></div>'
                        f'{detail}</div>')
        groups.append((n_open == 0, f'<details class="grp" name="rvgrp" data-src="{html.escape(key, quote=True)}">'
                      f'<summary><span class="gt">{html.escape(title)}</span>'
                      f'<span class="gs">{html.escape(summary_of(path.read_text(errors="ignore"), manifest[key].get("note", "")))}</span>'
                      f'<span class="gm">{chips}<a href="/{folder}/{key}" target="_blank">Full page</a>{stale}</span></summary>'
                      f'<div class="gb">{"".join(body)}</div></details>'))
    groups.sort(key=lambda g: g[0])
    out = [g for _, g in groups]
    name = NAMES.get(folder, folder)
    stale_pages = stale_log(folder)
    extra_attrs = (' data-review-skip="on"' if skip else "") + \
                  (f' data-review-import="{html.escape(imports[0], quote=True)}"' if imports else "") + \
                  (f' data-review-stale="{html.escape("|".join(stale_pages), quote=True)}"' if stale_pages else "")
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)}: everything open for review</title>
<link rel="stylesheet" href="/_site/site.css?v=11">
</head>
<body class="site unified" data-tz="{html.escape(SITE.get("timezone", ""), quote=True)}" data-review-page="/{folder}/review/" data-review-h2="off" data-review-reset="{html.escape("|".join(resets), quote=True)}" data-review-approved="{",".join(approved)}" data-review-reopen="{html.escape("|".join(reopen), quote=True)}"{extra_attrs}>
<header class="top"><div class="wrap">
<h1>{html.escape(name)}: everything open for review</h1>
<p>{open_n} open items from {len(out)} pages. Open a page, answer each item Yes, No or Changes (Changes needs a note), then use More, Copy results and paste it into the {html.escape(folder.upper())} session. Press Stale on a page that no longer matters. Approved items are hidden and stay in Copy results. <a href="../">All {html.escape(name)} pages</a></p>
</div></header>
<main class="wrap">
{"".join(out) or '<p class="empty">Nothing open.</p>'}
</main>
<script src="/_site/review.js?v=11"></script>
</body></html>
'''
    (fdir / "review").mkdir(exist_ok=True)
    (fdir / "review" / "index.html").write_text(page)
    print(f"{folder}: open={open_n} approved={len(approved)} reopened={len(reopen)} pages={len(out)}")


if __name__ == "__main__":
    own = SITE.get("builders", {})
    for f in sys.argv[1:] or [f["id"] for f in SITE.get("folders", []) if f["id"] not in own]:
        if f in own:
            sys.exit(f"{f}/review/ is built by its own builder ({own[f]}, see site.json builders)")
        main(f)

#!/usr/bin/env python3
"""Build /<folder>/review/index.html: one page holding every item of the folder's needs-you pages
(from <folder>/_status.json), grouped by source page. Each group is collapsed (one open at a time) and
its heading shows the page title, a one-line summary, the open count, its chips and a Stale button.
Each item shows its question and answer controls first; bulky content sits behind "Show details" in an
iframe with its page's CSS. Items come from [data-review-question] sections, or from <h2> sections on plain pages.
Approved, reopened, blocked and reset attributes on the source pages carry through, prefixed by page.
A page's own answer choices (data-review-options / data-review-default) are copied onto each of its items.

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


def parse_options(spec):
    pairs = [p.split(":", 1) for p in spec.split(",") if ":" in p]
    return [(v.strip(), lab.strip()) for v, lab in pairs if v.strip() and lab.strip()]


def choices_of(tag, body):
    """An item's answer choices, by the rule review.js uses: the item's own data-review-options, else
    the page's. The default is dropped when it isn't one of the choices. None for Yes / No / Changes."""
    own = parse_options(attr(tag, "data-review-options"))
    opts = own or parse_options(attr(body, "data-review-options"))
    if not opts:
        return None
    d = attr(tag, "data-review-default") or attr(body, "data-review-default")
    return {"options": opts, "default": d if any(v == d for v, _ in opts) else ""}


def options_attr(choice):
    return ",".join(f"{v}:{lab}" for v, lab in choice["options"])


def tally(choices):
    """'0 start · 3 hold': the per-choice counts a choices group shows until review.js has the saved answers."""
    counts = {}
    for c in choices:
        for _, lab in c["options"]:
            counts.setdefault(lab.lower(), 0)
        lab = dict(c["options"]).get(c["default"])
        if lab:
            counts[lab.lower()] += 1
    return " · ".join(f"{n} {k}" for k, n in counts.items())


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
            items.append((sid, t, chunk, attr(tag, "data-review-type"), attr(tag, "data-suggested"), choices_of(tag, body)))
    elif attr(body, "data-review-h2") != "off":
        for i, ch in enumerate([c for c in re.split(r"(?=<h2[\s>])", inner) if c.startswith("<h2")], 1):
            h2tag = re.match(r"<h2[^>]*>", ch).group(0)
            t = re.sub(r"<[^>]+>", "", re.match(r"<h2[^>]*>(.*?)</h2>", ch, re.S).group(1)).strip()
            items.append((f"s{i}", html.unescape(t), ch, attr(h2tag, "data-review-type"), attr(h2tag, "data-suggested"), choices_of(h2tag, body)))
    # Choice items (the page's own answer choices) are never approved or open; questions never take choices.
    items = [(sid, t, ch, typ, sug, None if typ == "question" else cho) for sid, t, ch, typ, sug, cho in items]
    out = [dict(id=f"{prefix}.{sid}", title=t, html=ch, approved=sid in approved and sid not in reopen and not cho,
                reopen=reopen.get(sid, ""), type=typ, suggested=sug, choice=cho) for sid, t, ch, typ, sug, cho in items]
    reset = attr(body, "data-review-reset")
    ver, _, ids = reset.partition(":")
    rids = [i.strip() for i in ids.split(",") if i.strip()] + [k for k in reopen if k not in ids.split(",")]
    tagged = f"{prefix}@{ver}:" + ",".join(f"{prefix}.{i}" for i in rids) if ver else ""
    blocked = dict(p.split("=", 1) for p in attr(body, "data-review-blocked").split("|") if "=" in p)
    extra = {"skip": attr(body, "data-review-skip") == "on", "import": attr(body, "data-review-import"),
             "build": attr(body, "data-build"), "blocked": {k.strip(): v.strip() for k, v in blocked.items()}}
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


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Elements whose end tag the parser infers: left alone, since an added or dropped one changes the layout.
OPTIONAL_END = {"p", "li", "dt", "dd", "option", "optgroup", "tr", "td", "th", "thead", "tbody", "tfoot", "colgroup", "rp", "rt"}
TAG = re.compile(r"<!--.*?-->|<(/?)([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*>", re.S)


def balance(chunk):
    """An <h2> section is cut out of its page at the next <h2>, so it can end inside a wrapper (the page's
    </main>) or open one it never closes. Drop closing tags with no opener in the chunk and close what is
    left open, so nothing escapes the item on the unified page."""
    out, stack, pos = [], [], 0
    for m in TAG.finditer(chunk):
        closing, name = m.group(1), (m.group(2) or "").lower()
        if not name or name in VOID or name in OPTIONAL_END or m.group(0).endswith("/>"):
            continue
        if not closing:
            stack.append(name)
        elif name in stack:
            while stack.pop() != name:
                pass
        else:
            out.append(chunk[pos:m.start()])
            pos = m.end()
    out.append(chunk[pos:])
    return "".join(out) + "".join(f"</{n}>" for n in reversed(stack))


def clean(chunk, title):
    """Drop page chrome (header/nav/footer) and the item's own heading, which the group already shows."""
    chunk = balance(CHROME.sub("", chunk))
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
    groups, approved, reopen, resets, open_n, skip, imports, blocked = [], [], [], [], 0, False, [], []
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
        blocked += [f"{prefix}.{k}={prefix}.{v}" for k, v in extra["blocked"].items()]
        is_blocked = {f"{prefix}.{k}" for k in extra["blocked"]}
        base = f"/{folder}/" + (key if key.endswith("/") else (key.rsplit("/", 1)[0] + "/" if "/" in key else ""))
        ync = [i for i in items if i.get("type") != "question" and not i["choice"]]
        choices = [i["choice"] for i in items if i["choice"]]
        n_open = sum(not i["approved"] and i["id"] not in is_blocked for i in ync)
        n_reo = sum(bool(i["reopen"]) for i in ync)
        # review.js finds this chip by data-open-chip and keeps it current as items are answered.
        chips = f'<span class="chip {"c-review" if n_open else "c-approved"}" data-open-chip>{n_open} open</span>'
        if choices and not ync:
            chips = f'<span class="chip" data-open-chip data-choice-chip>{html.escape(tally(choices))}</span>'
        chips += chip("Reopened", "c-reopened") if n_reo else ""
        n_appr = sum(bool(i["approved"]) for i in ync)
        chips += chip(f"{n_appr} approved", "c-approved") if n_appr and n_open else ""
        chips += "".join(chip(c) for c in manifest[key].get("chips", []) if c)
        stale = "" if f"{folder}/{key}" in protected else (
            f'<button type="button" class="stale-btn" data-stale-folder="{html.escape(folder, quote=True)}" '
            f'data-stale-page="{html.escape(key, quote=True)}" data-stale-title="{html.escape(title, quote=True)}">Stale: remove this page</button>')
        body = []
        for it in items:
            is_q = it.get("type") == "question"
            if is_q or it["choice"]:
                pass  # never counted in approved/open: a free-text question or one of the page's own choices
            elif it["approved"]:
                approved.append(it["id"])
            elif it["id"] not in is_blocked:
                open_n += 1
            if not is_q and it["reopen"]:
                reopen.append(f'{it["id"]}={it["reopen"]}')
            chunk = clean(it["html"], it["title"])
            small = len(text_of(chunk)) <= 400 and not BULKY.search(chunk)
            detail = (f'<div class="lead">{chunk}</div>' if small and text_of(chunk) else "") if small else \
                f'<details class="rv-details"><summary>Show details</summary>{frame(styles, chunk, base)}</details>'
            type_attr = f' data-review-type="{html.escape(it["type"], quote=True)}"' if it.get("type") else ""
            sugg_attr = f' data-suggested="{html.escape(it["suggested"], quote=True)}"' if it.get("suggested") else ""
            if it["choice"]:
                sugg_attr += (f' data-review-options="{html.escape(options_attr(it["choice"]), quote=True)}"'
                              f' data-review-default="{html.escape(it["choice"]["default"], quote=True)}"')
            body.append(f'<div class="item" data-review-question="{html.escape(it["id"], quote=True)}" '
                        f'data-title="{html.escape(title + ": " + it["title"], quote=True)}"{type_attr}{sugg_attr}>'
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
                  (f' data-review-stale="{html.escape("|".join(stale_pages), quote=True)}"' if stale_pages else "") + \
                  (f' data-review-blocked="{html.escape("|".join(blocked), quote=True)}"' if blocked else "")
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(name)}: everything open for review</title>
<link rel="stylesheet" href="/_site/site.css?v=22">
<script src="/_site/theme.js?v=20"></script>
</head>
<body class="site unified" data-tz="{html.escape(SITE.get("timezone", ""), quote=True)}" data-review-page="/{folder}/review/" data-review-h2="off" data-review-reset="{html.escape("|".join(resets), quote=True)}" data-review-approved="{",".join(approved)}" data-review-reopen="{html.escape("|".join(reopen), quote=True)}"{extra_attrs}>
<header class="top"><div class="wrap">
<h1>{html.escape(name)}: everything open for review</h1>
<p><span class="open-total">{open_n}</span> open items from {len(out)} pages. Open a page, answer each item Yes, No or Changes (Changes needs a note), then use More, Copy results and paste it into the {html.escape(folder.upper())} session. Press Stale on a page that no longer matters. Approved items are hidden and stay in Copy results. <a href="../">All {html.escape(name)} pages</a></p>
</div></header>
<main class="wrap">
{"".join(out) or '<p class="empty">Nothing open.</p>'}
</main>
<script src="/_site/review.js?v=23"></script>
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

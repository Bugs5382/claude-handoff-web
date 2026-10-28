#!/usr/bin/env python3
"""The agent's command line for page files and its inbox. Every write goes through pagefile.py.

  page.py new <folder>/<slug> [--from FILE]       create a page from a definition (JSON on stdin or FILE)
  page.py set <folder>/<slug> [--from FILE]       replace a page's definition
  page.py reply <page> <id|_page> --from AGENT [--reopen REASON | --action ACTION] [--reason R] [--ref REF] TEXT
  page.py status <page> <needs-you|reference|done> [--note N] [--chip C ...] [--priority P]
  page.py route <page> --to AGENT --mode <send|copy|both>
  page.py round-close <page> [--results TEXT]     Save round now
  page.py check <page|file> ...                   validate; prints errors with their JSON path, exit 1 on any
  page.py wait <agent> [--timeout S] [--poll]     block until a submission is in _inbox/<agent>/, print the files
                                                  (blockers first) and exit; exit 3 on --timeout with nothing
  page.py hook <agent>                            one line when the inbox has untaken files or nothing listens
  page.py convert <page>.html [--print]           turn a review.js page into a page file, importing its saved
                                                  answers and round history; --print shows the definition only

--root sets the site folder (default: the folder above _site/).
"""
import argparse
import html
import json
import os
import re
import select
import signal
import sys
import time
from datetime import datetime
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pagefile  # noqa: E402
import schema  # noqa: E402
from serve import AGENT_RE, PAGE_SEG_RE, page_key  # noqa: E402

ANSWER_MAP = {"yes": "yes", "no": "no", "chg": "changes", "skip": "skipped"}


class CliError(Exception):
    pass


def page_path(root, ref, must_exist=True):
    """<folder>/<slug> (or deeper) to its file, or a .json path as given."""
    if ref.endswith(".json"):
        return ref
    parts = ref.strip("/").split("/")
    if len(parts) < 2 or not all(PAGE_SEG_RE.match(x) for x in parts):
        raise CliError(f"{ref}: expected <folder>/<slug>, such as app/design")
    path = os.path.join(root, *parts) + ".json"
    if must_exist and not os.path.isfile(path):
        raise CliError(f"{ref}: no such page")
    return path


def read_definition(src):
    try:
        if src in (None, "-"):
            return json.load(sys.stdin)
        with open(src, encoding="utf-8") as f:
            return json.load(f)
    except ValueError as e:
        raise CliError(f"the definition is not JSON: {e}") from None


def cmd_new(a):
    path = page_path(a.root, a.page, must_exist=False)
    if os.path.exists(path):
        raise CliError(f"{a.page} already exists; use set")
    definition = read_definition(a.source)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pagefile.write_definition(path, definition)
    print(f"created {a.page}")


def cmd_set(a):
    path = page_path(a.root, a.page)
    rev = pagefile.write_definition(path, read_definition(a.source))
    print(f"{a.page} at rev {rev}")


def cmd_reply(a):
    action, reason = a.action, a.reason
    if a.reopen is not None:
        action, reason = "reopen", a.reopen
    n = pagefile.reply(page_path(a.root, a.page), a.item, a.sender, a.text, action=action, reason=reason, ref=a.ref)
    print(f"reply {n} on {a.item}")


def cmd_status(a):
    pagefile.set_status(page_path(a.root, a.page), a.state, note=a.note, chips=a.chip, priority=a.priority)
    print(f"{a.page} is {a.state}")


def cmd_route(a):
    pagefile.set_route(page_path(a.root, a.page), a.to, a.mode)
    print(f"{a.page} routes to {a.to} ({a.mode})")


def cmd_round_close(a):
    n = pagefile.new_round(page_path(a.root, a.page), results=a.results)
    print(f"round {n} open")


def cmd_check(a):
    bad = 0
    for ref in a.pages:
        try:
            with open(page_path(a.root, ref), encoding="utf-8") as f:
                errors = schema.validate(json.load(f))
        except ValueError as e:
            errors = [f"(page): not JSON: {e}"]
        for err in errors:
            print(f"{ref}: {err}" if len(a.pages) > 1 else err)
        bad += bool(errors)
    return 1 if bad else 0


def inbox_dir(root, agent):
    if not AGENT_RE.match(agent):
        raise CliError(f"{agent}: expected an agent name like ops or app")
    return os.path.join(root, "_inbox", agent)


def waiting(inbox):
    """Submission files waiting in an inbox, sorted so blockers (0-) come before sends (5-)."""
    try:
        return sorted(e.name for e in os.scandir(inbox) if e.is_file() and e.name.endswith(".json") and not e.name.startswith("."))
    except FileNotFoundError:
        return []


def _block(inbox, deadline, poll, interval):
    """Wait for the inbox folder to change: kqueue where there is one, else a scan every interval seconds."""
    if not poll and hasattr(select, "kqueue"):
        fd = os.open(inbox, os.O_RDONLY)
        try:
            kq = select.kqueue()
            ev = select.kevent(fd, filter=select.KQ_FILTER_VNODE, flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                               fflags=select.KQ_NOTE_WRITE)
            while not waiting(inbox):
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    return
                kq.control([ev], 1, left)
        finally:
            os.close(fd)
        return
    while not waiting(inbox):
        if deadline is not None and time.monotonic() >= deadline:
            return
        time.sleep(interval)


def cmd_wait(a):
    inbox = inbox_dir(a.root, a.agent)
    os.makedirs(inbox, exist_ok=True)
    listening = os.path.join(inbox, ".listening")
    with open(listening, "w") as f:
        f.write(str(os.getpid()))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(129))
    deadline = None if a.timeout is None else time.monotonic() + a.timeout
    try:
        if not waiting(inbox):
            _block(inbox, deadline, a.poll, a.interval)
            # A Send and a Blocker often land together; give the second one a moment so both are listed.
            time.sleep(a.debounce)
        names = waiting(inbox)
    finally:
        try:
            with open(listening) as f:
                mine = f.read().strip() == str(os.getpid())
            if mine:
                os.remove(listening)
        except OSError:
            pass
    for n in names:
        print(os.path.join(inbox, n))
    return 0 if names else 3


def cmd_hook(a):
    from serve import is_listening
    inbox = inbox_dir(a.root, a.agent)
    names = waiting(inbox)
    live = is_listening(a.root, a.agent)
    again = f"python3 {os.path.abspath(__file__)} wait {a.agent}"
    if names:
        s = "" if len(names) == 1 else "s"
        print(f"handoff: {len(names)} submission{s} waiting for {a.agent} in {inbox}; take them, act, and reply on the page"
              + ("" if live else f", then start `{again}` in the background again"))
    elif not live:
        print(f"handoff: nothing is listening for {a.agent}; start `{again}` in the background")
    return 0


# ---- convert: a review.js page to a page file ----

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Node:
    def __init__(self, tag, attrs):
        self.tag, self.attrs, self.children = tag, attrs, []

    def find_all(self, pred):
        for c in self.children:
            if isinstance(c, Node):
                if pred(c):
                    yield c
                yield from c.find_all(pred)

    def first(self, tag):
        return next(self.find_all(lambda n: n.tag == tag), None)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(src):
    t = _Tree()
    t.feed(src)
    t.close()
    return t.root


def text_of(node):
    if isinstance(node, str):
        return node
    return "".join(text_of(c) for c in node.children)


def squash(s):
    return re.sub(r"\s+", " ", s).strip()


def inline(node):
    """A node's content as the renderer's inline markup: **bold**, *em*, `code` and [text](url)."""
    if isinstance(node, str):
        return node
    inner = "".join(inline(c) for c in node.children)
    if node.tag in ("strong", "b"):
        return f"**{inner}**"
    if node.tag in ("em", "i"):
        return f"*{inner}*"
    if node.tag == "code":
        return f"`{text_of(node)}`"
    if node.tag == "a" and node.attrs.get("href"):
        return f"[{inner}]({node.attrs['href']})"
    if node.tag == "br":
        return " "
    return inner


def serialize(node):
    if isinstance(node, str):
        return html.escape(node, quote=False)
    attrs = "".join(f' {k}="{html.escape(v)}"' for k, v in node.attrs.items())
    if node.tag in VOID:
        return f"<{node.tag}{attrs}>"
    return f"<{node.tag}{attrs}>" + "".join(serialize(c) for c in node.children) + f"</{node.tag}>"


def _images_only(node):
    imgs = []
    for c in node.children:
        if isinstance(c, str):
            if c.strip():
                return None
        elif c.tag == "img":
            imgs.append(c)
        elif c.tag == "a" and all(isinstance(x, str) and not x.strip() or isinstance(x, Node) and x.tag == "img" for x in c.children):
            imgs += [x for x in c.children if isinstance(x, Node)]
        elif c.tag == "br":
            continue
        else:
            return None
    return imgs or None


def _image(img):
    b = {"image": img.attrs.get("src", "")}
    if img.attrs.get("alt"):
        b["alt"] = img.attrs["alt"]
    return b


def _diff_text(node, drop):
    if isinstance(node, str):
        return node
    if node.tag == drop:
        return ""
    return "".join(_diff_text(c, drop) for c in node.children)


def blocks(nodes, warn):
    """Body blocks from a run of HTML nodes. What has no block becomes a flagged html block."""
    out = []
    for n in nodes:
        if isinstance(n, str):
            if n.strip():
                out.append({"p": squash(n)})
            continue
        tag, cls = n.tag, n.attrs.get("class", "").split()
        if tag in ("script", "style", "template"):
            continue
        if tag == "p":
            imgs = _images_only(n)
            out += [_image(i) for i in imgs] if imgs else ([{"p": squash(inline(n))}] if squash(inline(n)) else [])
        elif tag in ("ul", "ol"):
            items = [squash(inline(li)) for li in n.children if isinstance(li, Node) and li.tag == "li"]
            start = n.attrs.get("start", "1")
            if tag == "ol" and start.isdigit() and start != "1":
                # A list that carries on from an earlier one keeps its numbers as text.
                out += [{"p": f"{int(start) + i}. {t}"} for i, t in enumerate(items)]
            else:
                out.append({"olist" if tag == "ol" else "list": items})
        elif tag == "pre":
            code = text_of(n)
            out.append({"code": code[1:] if code.startswith("\n") else code})
        elif tag == "img":
            out.append(_image(n))
        elif tag == "a" and n.first("img") is not None and not squash(text_of(n)):
            out += [_image(i) for i in n.find_all(lambda x: x.tag == "img")]
        elif tag == "table" and n.find_all(lambda x: x.tag in ("th", "td") and ("colspan" in x.attrs or "rowspan" in x.attrs)):
            warn("kept a <table> with merged cells as an html block")
            out.append({"html": serialize(n)})
        elif tag == "table":
            rows = [[squash(inline(c)) for c in tr.children if isinstance(c, Node) and c.tag in ("th", "td")]
                    for tr in n.find_all(lambda x: x.tag == "tr")]
            out.append({"table": rows})
        elif tag == "div" and "rvdiff" in cls:
            code = "code" in cls
            paras = [c for c in n.children if isinstance(c, Node) and c.tag == "p"]
            joiner = "\n" if code else "\n\n"
            old = joiner.join(_diff_text(p, "ins").strip("\n") for p in paras)
            new = joiner.join(_diff_text(p, "del").strip("\n") for p in paras)
            out.append({"diff": {"old": old, "new": new, "code": code}})
        elif tag in ("h3", "h4", "h5", "h6"):
            out.append({"p": f"**{squash(inline(n))}**"})
        elif tag == "blockquote":
            out.append({"note": squash(inline(n))})
        elif tag in ("div", "section") and not n.attrs.get("data-review-question"):
            out += blocks(n.children, warn)
        else:
            warn(f"kept a <{tag}> as an html block")
            out.append({"html": serialize(n)})
    return out


def _flatten(nodes):
    """Top-level nodes, opening plain wrappers that hold an h2 so every h2 sits at the top."""
    out = []
    for n in nodes:
        if (isinstance(n, Node) and n.tag in ("div", "section", "article") and not n.attrs.get("data-review-question")
                and n.first("h2") is not None):
            out += _flatten(n.children)
        else:
            out.append(n)
    return out


def _question(item, el):
    if el.attrs.get("data-review-type") == "question":
        item["type"] = "question"
        if el.attrs.get("data-suggested"):
            item["suggested"] = el.attrs["data-suggested"]


def convert_html(src, name, manifest_entry, warn_out):
    """(definition, extras) for a review.js page. extras holds what belongs to the rounds, not the definition."""
    doc = parse_html(src)
    body = doc.first("body") or doc
    battrs = body.attrs
    main = body.first("main") or body
    title_el = doc.first("title")
    title = squash(text_of(title_el)) if title_el else ""
    if not title:
        h1 = body.first("h1")
        title = squash(text_of(h1)) if h1 else name
    items = []

    def warner(iid):
        return lambda msg: warn_out(f"{name}: {iid}: {msg}")

    if battrs.get("data-review-h2") == "off":
        for el in main.find_all(lambda n: bool(n.attrs.get("data-review-question"))):
            iid = el.attrs["data-review-question"].lower()
            h2 = el.first("h2")
            item = {"id": iid, "title": el.attrs.get("data-title") or (squash(text_of(h2)) if h2 else iid)}
            _question(item, el)
            rest = [c for c in el.children if c is not h2]
            item["body"] = blocks(rest, warner(iid))
            howto = next(el.find_all(lambda n: n.tag == "template" and "data-howto" in n.attrs), None)
            if howto is not None:
                item["howto"] = blocks(howto.children, warner(iid))
            items.append(item)
    else:
        intro, current, n = [], None, 0
        for node in _flatten(main.children):
            if isinstance(node, Node) and node.tag == "h2":
                n += 1
                current = {"id": f"s{n}", "title": squash(text_of(node)), "_nodes": []}
                _question(current, node)
                if node.attrs.get("data-review-options"):
                    warn_out(f"{name}: s{n}: its own choices aren't kept; the page's apply")
                items.append(current)
            elif current is None:
                intro.append(node)
            else:
                current["_nodes"].append(node)
        intro_blocks = blocks(intro, warner("intro"))
        for it in items:
            it["body"] = blocks(it.pop("_nodes"), warner(it["id"]))
        if intro_blocks:
            items.insert(0, {"id": "intro", "type": "info", "title": "About this page", "body": intro_blocks})
    seen = {}
    for it, raw in zip(items, _raw_ids(main, battrs, items), strict=True):
        if it["id"] in seen:
            raise CliError(f"{name}: ids {seen[it['id']]} and {raw} only differ by case")
        seen[it["id"]] = raw
        if not it["body"]:
            del it["body"]

    options = None
    pairs = [p.partition(":") for p in battrs.get("data-review-options", "").split(",")]
    choices = [{"value": v.strip(), "label": lab.strip()} for v, _, lab in pairs if v.strip() and lab.strip()]
    if choices:
        options = {"choices": choices}
        if battrs.get("data-review-default") in {c["value"] for c in choices}:
            options["default"] = battrs["data-review-default"]
    skip = battrs.get("data-review-skip") == "on"
    build = battrs.get("data-build") or None
    uses_review = any("review.js" in n.attrs.get("src", "") for n in doc.find_all(lambda n: n.tag == "script"))
    kind = "backlog" if options else ("checklist" if skip and build else "review" if uses_review else "reference")
    if skip and kind == "review":
        for it in items:
            if it.get("type") not in ("question", "info"):
                it["skip"] = True

    ids = {it["id"] for it in items}
    for part in battrs.get("data-review-blocked", "").split("|"):
        target, _, why = part.partition("=")
        target, why = target.strip().lower(), why.strip()
        it = next((x for x in items if x["id"] == target), None)
        if not it or not why:
            continue
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9_-]*", why)
        dep = m.group(0).lower() if m else None
        if dep in ids and dep != target:
            it["dependsOn"] = [dep]
        else:
            it["blockedBy"] = why

    definition = {"schema": pagefile.SCHEMA, "kind": kind, "title": title}
    meta = next(doc.find_all(lambda n: n.tag == "meta" and n.attrs.get("name") == "description"), None)
    if meta is not None and meta.attrs.get("content", "").strip():
        definition["summary"] = squash(meta.attrs["content"])
    if build:
        definition["build"] = build
    reset = battrs.get("data-review-reset", "").split(":")[0]
    digits = re.sub(r"\D", "", reset)
    if digits:
        definition["reset"] = int(digits)
    if manifest_entry:
        st = {"state": manifest_entry.get("state", "needs-you")}
        for k in ("note", "chips", "priority"):
            if manifest_entry.get(k) not in (None, "", []):
                st[k] = manifest_entry[k]
        definition["status"] = st
    if options:
        definition["options"] = options
    definition["items"] = items
    for attr in ("data-review-import", "data-review-stale"):
        if battrs.get(attr):
            warn_out(f"{name}: {attr} isn't carried over")
    extras = {
        "approved": [x.strip().lower() for x in battrs.get("data-review-approved", "").split(",") if x.strip().lower() in ids],
        "reopened": {k.strip().lower(): v.strip() for k, _, v in (p.partition("=") for p in battrs.get("data-review-reopen", "").split("|"))
                     if k.strip().lower() in ids and v.strip()},
    }
    return definition, extras


def _raw_ids(main, battrs, items):
    """Each item's id as the page wrote it, for naming ids that clash once lower-cased."""
    if battrs.get("data-review-h2") != "off":
        return [it["id"] for it in items]
    return [el.attrs["data-review-question"] for el in main.find_all(lambda n: bool(n.attrs.get("data-review-question")))]


def _answer(saved, item_ids):
    """Saved review.js answers ({id: {v, n} or {a}}) as page file answers {id: (answer, note)}."""
    out = {}
    for iid, v in (saved or {}).items():
        iid = iid.lower()
        if iid not in item_ids or not isinstance(v, dict):
            continue
        if "a" in v:
            answer, note = str(v.get("a") or ""), ""
        else:
            answer, note = ANSWER_MAP.get(v.get("v") or "", v.get("v") or ""), str(v.get("n") or "")
        if answer or note:
            out[iid] = (answer, note)
    return out


def _entries(pairs, items, by, at):
    return {iid: {"answer": answer, "note": note, "by": by, "at": at, "hash": pagefile.item_hash(items[iid])}
            for iid, (answer, note) in pairs.items()}


def cmd_convert(a):
    src_path = os.path.abspath(a.html)
    root = os.path.abspath(a.root)
    rel = os.path.relpath(src_path, root).replace(os.sep, "/")
    if rel.startswith("../") or not rel.endswith(".html"):
        raise CliError(f"{a.html}: expected an .html page inside {root}")
    folder, key = rel.split("/", 1)
    slug_rel = rel[:-len("/index.html")] if rel.endswith("/index.html") else rel[:-5]
    with open(src_path, encoding="utf-8", errors="replace") as f:
        src = f.read()
    try:
        with open(os.path.join(root, folder, "_status.json")) as f:
            entry = json.load(f).get(key if not key.endswith("index.html") else key[:-len("index.html")])
    except (OSError, ValueError):
        entry = None
    name = os.path.basename(slug_rel)
    definition, extras = convert_html(src, name, entry, lambda m: print(f"convert: {m}", file=sys.stderr))
    if a.print:
        print(json.dumps(definition, indent=2, ensure_ascii=False))
        return 0
    path = page_path(root, slug_rel, must_exist=False)
    if os.path.exists(path):
        raise CliError(f"{slug_rel} already exists")
    errors = schema.validate(dict(definition, rev=0, rounds=[{"round": 1, "opened": "x", "closed": None, "openedBy": "x", "answers": {}}],
                                  thread={}, submissions=[]))
    if errors:
        raise pagefile.PageError(errors)
    cfg = {}
    try:
        with open(os.path.join(root, "site.json")) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        pass
    by = cfg.get("owner", "owner")
    items = {it["id"]: it for it in definition["items"]}
    pkey = page_key(cfg.get("key_prefix", "review:") + "/" + (rel[:-len("index.html")] if rel.endswith("/index.html") else rel))
    rounds = []
    hdir = os.path.join(root, "_saved", "history", pkey)
    history = []
    if os.path.isdir(hdir):
        for fn in sorted(os.listdir(hdir)):
            try:
                with open(os.path.join(hdir, fn)) as f:
                    history.append(json.load(f))
            except (OSError, ValueError):
                continue
    history.sort(key=lambda h: h.get("round") if isinstance(h.get("round"), int) else 0)
    if [h.get("round") for h in history] != list(range(1, len(history) + 1)):
        print(f"convert: {name}: history rounds weren't 1, 2, 3...; renumbered in order", file=sys.stderr)
    for n, h in enumerate(history, 1):
        closed = h.get("closed") or h.get("opened") or pagefile.now_iso()
        r = {"round": n, "build": h.get("build") or None, "reset": None, "opened": h.get("opened") or closed, "closed": closed,
             "openedBy": "imported", "answers": _entries(_answer(h.get("answers"), items), items, by, closed),
             "checkpoints": {}, "reopened": {}}
        if isinstance(h.get("results_text"), str):
            r["results"] = h["results_text"]
        rounds.append(r)
    saved_fn = os.path.join(root, "_saved", pkey + ".json")
    saved, at = {}, pagefile.now_iso()
    if os.path.isfile(saved_fn):
        try:
            with open(saved_fn) as f:
                saved = json.load(f)
            at = datetime.fromtimestamp(os.path.getmtime(saved_fn)).astimezone().isoformat(timespec="seconds")
        except (OSError, ValueError):
            saved = {}
    current = _answer(saved, items)
    last = rounds[-1]["answers"] if rounds else {}
    for iid in extras["approved"]:
        before = last.get(iid)
        if before and before["answer"] == "yes" and current.get(iid, ("yes", before["note"])) in (("yes", before["note"]), ("yes", "")):
            # Already Yes in the last closed round: leaving it out of the open round keeps it hidden, as before.
            current.pop(iid, None)
        else:
            current.setdefault(iid, ("yes", ""))
    rounds.append({"round": len(rounds) + 1, "build": definition.get("build"), "reset": definition.get("reset"),
                   "opened": rounds[-1]["closed"] if rounds else at, "closed": None, "openedBy": "imported",
                   "answers": _entries(current, items, by, at), "checkpoints": {},
                   "reopened": {k: v for k, v in extras["reopened"].items() if k not in current}})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pagefile.write_definition(path, definition, now=at)
    pagefile.import_rounds(path, rounds)
    op = cfg.get("operator") if isinstance(cfg.get("operator"), str) else "ops"
    for iid, why in extras["reopened"].items():
        if iid in current:
            # Answered again since it reopened: the reason stays readable under the item.
            pagefile.reply(path, iid, op, f"Reopened: {why}", action="info", now=rounds[-1]["opened"])
    print(f"converted {rel} to {slug_rel} ({len(rounds)} round{'s' if len(rounds) != 1 else ''})")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="page.py", description="Page files and the inbox, for agents.")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), help="the site folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("new", cmd_new), ("set", cmd_set)):
        p = sub.add_parser(name)
        p.add_argument("page")
        p.add_argument("--from", dest="source", help="the definition file (default: stdin)")
        p.set_defaults(fn=fn)
    p = sub.add_parser("reply")
    p.add_argument("page")
    p.add_argument("item")
    p.add_argument("text")
    p.add_argument("--from", dest="sender", required=True)
    p.add_argument("--reopen", metavar="REASON")
    p.add_argument("--action", choices=schema.ACTIONS)
    p.add_argument("--reason")
    p.add_argument("--ref")
    p.set_defaults(fn=cmd_reply)
    p = sub.add_parser("status")
    p.add_argument("page")
    p.add_argument("state", choices=schema.STATES)
    p.add_argument("--note")
    p.add_argument("--chip", action="append")
    p.add_argument("--priority", type=int)
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("route")
    p.add_argument("page")
    p.add_argument("--to", required=True)
    p.add_argument("--mode", required=True, choices=schema.MODES)
    p.set_defaults(fn=cmd_route)
    p = sub.add_parser("round-close")
    p.add_argument("page")
    p.add_argument("--results")
    p.set_defaults(fn=cmd_round_close)
    p = sub.add_parser("check")
    p.add_argument("pages", nargs="+")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("wait")
    p.add_argument("agent")
    p.add_argument("--timeout", type=float)
    p.add_argument("--poll", action="store_true", help="scan the folder instead of using kqueue")
    p.add_argument("--interval", type=float, default=2.0, help=argparse.SUPPRESS)
    p.add_argument("--debounce", type=float, default=0.2, help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_wait)
    p = sub.add_parser("hook")
    p.add_argument("agent")
    p.set_defaults(fn=cmd_hook)
    p = sub.add_parser("convert")
    p.add_argument("html")
    p.add_argument("--print", action="store_true", help="print the definition instead of writing the page file")
    p.set_defaults(fn=cmd_convert)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.root = os.path.abspath(a.root)
    try:
        return a.fn(a) or 0
    except CliError as e:
        print(f"page.py: {e}", file=sys.stderr)
        return 1
    except pagefile.PageError as e:
        for err in e.errors:
            print(f"page.py: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

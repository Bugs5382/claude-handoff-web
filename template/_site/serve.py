#!/usr/bin/env python3
"""Static file server for the hand-off site, plus a tiny JSON save store.

Serves a directory exactly like `python3 -m http.server`, and adds:
  PUT  /_save/<name>.json  store a JSON body (max 256 KB) in <root>/_saved/<name>.json, atomically; 204
  GET  /_save/<name>.json  return it, or 404
  POST /_stale             {"folder": "...", "page": "..."}: delete a needs-you page listed in that folder's
                           _status.json, mark it done there, rebuild the indexes, log it in _saved/stale-log.json
  GET  /_history/<page-key>/            list of past rounds for that page (newest first)
  GET  /_history/<page-key>/<file>      one archived round, read-only
  POST /_round-close       {"name": "<page-key>", "results_text": "..." (optional)}: archive the
                           current round by hand, same as an automatic rollover
Page files (<folder>/<slug>.json in handoff.page/v1, written only through pagefile.py; see PAGE-FILE.md):
  GET  /<folder>/<slug>                  the renderer shell, _site/page.html; an old <slug>.html URL redirects here
  GET  /_page/<folder>/<slug>            {page, states, summary, route, listening}, with an ETag for If-None-Match
  PUT  /_page/<folder>/<slug>/answers    {"base": rev, "answers": {id: {answer, note}}}: merge into the open round
  POST /_page/<folder>/<slug>/round      {"results": "..."}: Save round now
  POST /_page/<folder>/<slug>/restart    {"checkpoint": "...", "results": "..."}: restart a journey, send a restart
  POST /_page/<folder>/<slug>/unlock     {}: take the lock off a sent page without waiting for the agent
  POST /_page/<folder>/<slug>/send       {"kind": "send"|"blocker", "items": [ids], "results": "..."}: write the
                                         submission to _inbox/<agent>/ for the page's route
  GET  /_index/ and /_index/<folder>     index cards built from the page files, merged with _status.json pages
  POST /_stale on a page file marks it done and moves it to <folder>/_old/ instead of deleting it.
Nothing else is writable, and <root>/_saved/ and <root>/_inbox/ are never served directly (history is only
reachable through /_history/).
Files under any _old/ folder older than prune_old_days are deleted hourly (logged in
_saved/prune-log.json); _saved/ itself, including history, is never walked by the pruner.

A round is one pass of answers on a page: its `data-build` value, or its `data-review-reset`
version. Every successful PUT to /_save/<name>.json compares the page's current `data-build` and
`data-review-reset` against what was last seen for it. When either changed, the answers that were
on disk before this PUT (the previous round's, about to be cleared or reopened by the page's own
reset logic) are archived to <root>/_saved/history/<name>/<UTC-stamp>__<label>.json before being
overwritten. Stale deletes the page itself but never its history.

Settings come from <root>/site.json (all optional here):
  {"owner": "<owner>", "host": "127.0.0.1", "port": 8000, "timezone": "UTC", "tz_label": "UTC",
   "protected": ["folder/page/"], "builders": {"folder": "../its-own-builder.py"},
   "prune_old": true, "prune_old_days": 7,
   "operator": "ops", "routes": {"folder": {"to": "app", "mode": "send"}}}
Command-line flags override host and port.
"""
import argparse
import datetime as dt
import functools
import hashlib
import html
import importlib.util
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diff as site_diff  # noqa: E402
import pagefile  # noqa: E402
from pageindex import PAGE_SEG_RE, discover_page_files, page_card, page_file  # noqa: E402,F401

MAX_BODY = 256 * 1024
AGENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")
PAGE_ACTIONS = {"PUT": ("answers",), "POST": ("round", "restart", "send", "unlock")}
SAVE_RE = re.compile(r"^/_save/([a-z0-9._-]{1,120})\.json$")
FOLDER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
PAGE_KEY_RE = r"[a-z0-9][a-z0-9._-]{0,119}"
HIST_FILE_RE = re.compile(r"^[0-9]{8}T[0-9]{6}(?:-[0-9]+)?Z__[a-z0-9._-]{1,80}\.json$")
HIST_LIST_RE = re.compile(r"^/_history/(" + PAGE_KEY_RE + r")/$")
HIST_ENTRY_RE = re.compile(r"^/_history/(" + PAGE_KEY_RE + r")/([0-9]{8}T[0-9]{6}(?:-[0-9]+)?Z__[a-z0-9._-]{1,80}\.json)$")
RESERVED = {"stale-log", "prune-log"}
STALE_LOCK = threading.Lock()
ROUND_LOCK = threading.Lock()
ANSWER_LABELS = {"yes": "YES", "no": "NO", "chg": "CHANGES", "skip": "SKIPPED (locked)"}


def atomic_write(fn, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(fn), prefix=".tmp-", suffix=os.path.splitext(fn)[1])
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(fn):
            shutil.copymode(fn, tmp)
        os.replace(tmp, fn)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def now_local(cfg):
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(cfg.get("timezone", "UTC")))
    except Exception:
        return dt.datetime.now().astimezone()


def load_config(root):
    try:
        with open(os.path.join(root, "site.json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def append_log(save_dir, name, entry):
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, name), "a") as f:
        f.write(json.dumps(entry) + "\n")


def _base36(n):
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def page_key(k):
    """Port of review.js's pageKey(): the sanitised name a page's answers (and now its round
    history) are stored under. Keep this in lock-step with the JS version in _site/review.js."""
    s = re.sub(r"[^a-z0-9._-]+", "-", k.lower())
    s = re.sub(r"^[-.]+|-+$", "", s)
    if len(s) > 120:
        h = 0
        for c in k:
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        s = s[:111] + "-" + _base36(h)
    return s or "page"


def discover_pages(root, cfg):
    """Map every page's /_save/ name to where it lives, the same one level deep under each folder
    that gen-index.py discovers. Used to find a page's HTML (for its round signature) from the
    opaque name a PUT or a /_history/ request carries."""
    prefix = cfg.get("key_prefix", "review:")
    ids = [f["id"] for f in cfg.get("folders", [])] if cfg.get("folders") else None
    if ids is None:
        try:
            ids = sorted(e for e in os.listdir(root) if not e.startswith((".", "_")) and os.path.isdir(os.path.join(root, e)))
        except OSError:
            ids = []
    out = {}
    for folder in ids:
        fdir = os.path.join(root, folder)
        if not os.path.isdir(fdir):
            continue
        try:
            entries = sorted(os.listdir(fdir))
        except OSError:
            continue
        for e in entries:
            if e.startswith(("_", ".")) or e == "index.html":
                continue
            full = os.path.join(fdir, e)
            if os.path.isdir(full):
                key, htmlpath = e + "/", os.path.join(full, "index.html")
            elif e.endswith(".html"):
                key, htmlpath = e, full
            else:
                continue
            if not os.path.isfile(htmlpath):
                continue
            page = f"/{folder}/{key}"
            out[page_key(prefix + page)] = {"folder": folder, "key": key, "path": htmlpath, "page": f"{folder}/{key}"}
    return out


def _body_attrs(src):
    m = re.search(r"<body\b[^>]*>", src, re.S)
    tag = m.group(0) if m else "<body>"
    return {am.group(1): html.unescape(am.group(2)) for am in re.finditer(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"', tag)}


def _page_title(src, default):
    m = re.search(r"<title>(.*?)</title>", src, re.S | re.I)
    if m:
        t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        if t:
            return re.sub(r"\s+", " ", t)
    return default


def _body_inner(src):
    m = re.search(r"<body\b[^>]*>", src, re.S)
    if not m:
        return ""
    return re.sub(r"<script\b.*?</script>", "", src[m.end():].split("</body>")[0], flags=re.S)


def _extract_items(src, attrs):
    """Best-effort (id, title) pairs for a page's review items, the same sources review.js uses:
    every <h2> (unless data-review-h2="off"), plus any [data-review-question] element."""
    inner = _body_inner(src)
    items = []
    if attrs.get("data-review-h2") != "off":
        for i, m in enumerate(re.finditer(r"<h2[^>]*>(.*?)</h2>", inner, re.S), 1):
            t = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            items.append((f"s{i}", re.sub(r"\s+", " ", t)))
    for tag in re.findall(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*\bdata-review-question="[^"]*"[^>]*>', inner):
        qm = re.search(r'data-review-question="([^"]*)"', tag)
        tm = re.search(r'data-title="([^"]*)"', tag)
        sid = html.unescape(qm.group(1))
        title = html.unescape(tm.group(1)) if tm else sid
        if not any(i[0] == sid for i in items):
            items.append((sid, title))
    return items


def _count_yes(answers):
    counted = [k for k, v in answers.items() if isinstance(v, dict) and not k.startswith(("_", "import:")) and not v.get("locked")]
    yes = sum(1 for k in counted if answers[k].get("v") == "yes")
    return yes, len(counted)


def _page_choices(attrs):
    """The page's own answer choices (body data-review-options and data-review-default), or None
    for a Yes / No / Changes page: {"labels": {value: label, ...}, "default": value or ""}."""
    labels = {}
    for part in attrs.get("data-review-options", "").split(","):
        value, _, label = part.partition(":")
        if value.strip() and label.strip():
            labels[value.strip()] = label.strip()
    if not labels:
        return None
    default = attrs.get("data-review-default", "")
    return {"labels": labels, "default": default if default in labels else ""}


def _results_text(page, title, src, attrs, answers, round_no, build):
    """Best-effort reconstruction of what the page's own Copy results would have shown for this
    round, from the page's current items and the round's saved answers."""
    items = _extract_items(src, attrs)
    choices = _page_choices(attrs)
    lines = [f"Round {round_no}: {title} (/{page})" + (f", build {build}" if build else "")]
    tally = {label.lower(): 0 for label in choices["labels"].values()} if choices else {}
    for sid, item_title in items:
        a = answers.get(sid) or {}
        if choices:
            # A page with its own choices: an item with no saved value is on the page's default.
            label = choices["labels"].get(a.get("v") or choices["default"], "")
            if label:
                tally[label.lower()] += 1
            answer = label.upper() if label else "NOT ANSWERED"
        else:
            answer = ANSWER_LABELS.get(a.get("v"), "NOT ANSWERED")
        lines.append(f"- [{sid}] {answer}: {item_title}")
        if a.get("n"):
            lines.append("    Note: " + str(a["n"]).replace("\n", " "))
    if choices:
        lines.append("")
        lines.append(" · ".join(f"{n} {k}" for k, n in tally.items()))
        return "\n".join(lines) + "\n"
    yes, counted = _count_yes({sid: answers.get(sid) or {} for sid, _ in items})
    if counted:
        lines.append("")
        lines.append("APPROVED: every item is Yes." if yes == counted else f"Not approved yet: {yes} of {counted} are Yes.")
    return "\n".join(lines) + "\n"


def _round_count(answers, src):
    """A round's one-line count for the History lists: "x of y Yes", or on a page with its own choices the
    per-choice counts the round's results text ends with ("1 start · 2 hold")."""
    attrs = _body_attrs(src)
    choices = _page_choices(attrs)
    if choices:
        tally = {label.lower(): 0 for label in choices["labels"].values()}
        for sid, _ in _extract_items(src, attrs):
            a = answers.get(sid) or {}
            label = choices["labels"].get(a.get("v") or choices["default"], "")
            if label:
                tally[label.lower()] += 1
        return " · ".join(f"{n} {k}" for k, n in tally.items())
    yes, counted = _count_yes(answers)
    return f"{yes} of {counted} Yes" if counted else "no items"


def _slug(s):
    return re.sub(r"[^a-z0-9._-]+", "-", (s or "").lower()).strip("-") or "round"


def _valid_save_name(name):
    return (isinstance(name, str) and bool(re.match(r"^[a-z0-9._-]{1,120}$", name))
            and not name.startswith(".") and name not in RESERVED)


def in_git_work_tree(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def page_path(root, folder, page):
    """Resolve a _status.json key to a deletable path inside root/folder, or None if it isn't one."""
    rel = page[:-1] if page.endswith("/") else page
    parts = rel.split("/")
    if not rel or rel.startswith("/") or "\\" in rel or any(x in ("", ".", "..") or x[0] in "_." for x in parts):
        return None
    if rel == "index.html" or rel == "review":
        return None
    fdir = os.path.realpath(os.path.join(root, folder))
    if os.path.dirname(fdir) != os.path.realpath(root):
        return None
    target = os.path.join(fdir, *parts)
    if os.path.islink(target) or os.path.realpath(target) != target:
        return None
    if not target.startswith(fdir + os.sep) or target == fdir:
        return None
    if page.endswith("/") != os.path.isdir(target) or not os.path.exists(target):
        return None
    return target


def prune_old(root, save_dir, days):
    """Delete files under every _old/ folder older than `days`; returns what was removed."""
    cutoff = time.time() - days * 86400
    removed = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if not (rel == "." and d == "_saved")]
        if "_old" not in rel.split(os.sep):
            continue
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                if not os.path.islink(full) and os.path.getmtime(full) < cutoff:
                    os.remove(full)
                    removed.append(os.path.relpath(full, root))
            except OSError:
                pass
    for dirpath, _dirs, _files in os.walk(root, topdown=False):
        rel = os.path.relpath(dirpath, root)
        parts = rel.split(os.sep)
        if "_old" in parts and parts[-1] != "_old" and not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    if removed:
        at = now_local(load_config(root)).isoformat(timespec="seconds")
        append_log(save_dir, "prune-log.json", {"at": at, "days": days, "removed": removed})
    return removed


def pruner(root, save_dir):
    while True:
        cfg = load_config(root)
        if cfg.get("prune_old", True):
            try:
                n = prune_old(root, save_dir, float(cfg.get("prune_old_days", 7)))
                if n:
                    print(f"pruned {len(n)} file(s) from _old/ folders", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"prune failed: {e}", file=sys.stderr, flush=True)
        time.sleep(3600)


def is_listening(root, agent):
    """True while _inbox/<agent>/.listening names a live process."""
    try:
        with open(os.path.join(root, "_inbox", agent, ".listening")) as f:
            pid = int(f.read().strip())
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False
    return True


def page_route(cfg, folder, doc):
    """The page's own route, else the folder's in site.json "routes", else send to the operator."""
    for rt in (doc.get("route"), (cfg.get("routes") or {}).get(folder)):
        if (isinstance(rt, dict) and isinstance(rt.get("to"), str) and AGENT_RE.match(rt["to"])
                and rt.get("mode") in ("send", "copy", "both")):
            return {"to": rt["to"], "mode": rt["mode"]}
    op = cfg.get("operator")
    return {"to": op if isinstance(op, str) and AGENT_RE.match(op) else "ops", "mode": "send"}


def submission_name(kind, rel, when):
    """Inbox file name: blockers and restarts (0) sort before sends (5); "{n}" is filled by pagefile."""
    prio = 5 if kind == "send" else 0
    return f"{prio}-{when.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{rel.replace('/', '-')}-{{n}}.json"


def page_diffs(doc):
    """Word-diff markup (diff.py) for every diff item ("<id>") and diff block ("<id>/body/<n>", "<id>/howto/<n>")."""
    out = {}
    for it in doc["items"]:
        if pagefile.item_type(doc, it) == "diff":
            out[it["id"]] = site_diff.diff_html(it.get("old", ""), it.get("new", ""), code=bool(it.get("code")))
        for key in ("body", "howto"):
            for n, b in enumerate(it.get(key) or [], 1):
                if isinstance(b, dict) and isinstance(b.get("diff"), dict):
                    d = b["diff"]
                    out[f"{it['id']}/{key}/{n}"] = site_diff.diff_html(d.get("old", ""), d.get("new", ""), code=bool(d.get("code")))
    return out


def load_gen_index(root):
    """The site's own gen-index.py as a module, for its collect() and order_pages(); None if it won't load."""
    fn = os.path.join(root, "gen-index.py")
    try:
        spec = importlib.util.spec_from_file_location("site_gen_index", fn)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def folder_cards(root, folder, gen):
    """Every card for a folder in index order: gen-index.py's collect() lists the HTML pages and the page files."""
    if gen is None:
        cards = [page_card(folder, rel, path) for rel, path in discover_page_files(root, folder)]
        return sorted(cards, key=lambda c: (c["priority"], c["key"]))
    return gen.collect(folder)


def site_folders(root, cfg):
    """(id, name, blurb) for every folder, in the root index's order (focus.json, then site.json order)."""
    folders = cfg.get("folders") or [{"id": e, "name": e} for e in sorted(os.listdir(root))
                                     if not e.startswith((".", "_")) and os.path.isdir(os.path.join(root, e))]
    try:
        with open(os.path.join(root, "_site", "focus.json")) as f:
            order = json.load(f).get("order") or cfg.get("order", [])
    except (OSError, ValueError, AttributeError):
        order = cfg.get("order", [])
    ids = [f["id"] for f in folders]
    ranked = [d for d in order if d in ids] + [d for d in ids if d not in order]
    by = {f["id"]: f for f in folders}
    return [(d, by[d].get("name", d), by[d].get("blurb", "")) for d in ranked]


class Handler(SimpleHTTPRequestHandler):
    save_dir = ""
    root = ""
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".md": "text/plain; charset=utf-8"}

    def _path(self):
        return urlsplit(self.path).path

    def end_headers(self):
        p = self._path()
        if (p.startswith(("/_save/", "/_history/", "/_stale", "/_round-close", "/_page/", "/_index/")) or p.endswith(".html")
                or p.endswith("/") or getattr(self, "_shell", False)):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _plain(self, code, text=""):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _save_name(self):
        m = SAVE_RE.match(self._path())
        if not m or m.group(1).startswith("."):
            return None
        if self.command == "PUT" and m.group(1) in RESERVED:
            return None
        return m.group(1)

    def _blocked(self):
        p = posixpath.normpath(unquote(self._path()))
        return any(p == d or p.startswith(d + "/") for d in ("/_saved", "/_inbox"))

    def do_GET(self):
        p = self._path()
        if p.startswith("/_save/"):
            return self._get_save()
        if p.startswith("/_history/"):
            return self._get_history()
        if p.startswith("/_page/"):
            return self._get_page()
        if p.startswith("/_index/"):
            return self._get_index()
        if self._blocked():
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        if self._page_url() or self._index_page():
            return
        return super().do_GET()

    def do_HEAD(self):
        if self._path().startswith(("/_save/", "/_history/", "/_page/", "/_index/")) or self._blocked():
            return self._plain(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

    def _page_url(self):
        """Serve the renderer shell for /<folder>/<slug>, or redirect a converted page's old .html URL.
        Anything that exists on disk is served as a file first."""
        p = self._path()
        if os.path.exists(self.translate_path(p)):
            return False
        rel = unquote(p).strip("/")
        if rel.endswith(".html") and page_file(self.root, rel[:-5]):
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", "/" + rel[:-5])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if p.endswith("/") or not page_file(self.root, rel):
            return False
        with open(os.path.join(self.root, "_site", "page.html"), "rb") as f:
            data = f.read()
        self._shell = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def _index_page(self):
        """Build /, /<folder>/ and /<folder>/history/ on request when page files are involved, with gen-index.py's
        own HTML, so their cards are always current. Folders without page files keep their static index.html."""
        p = self._path()
        m = re.match(r"^/(?:([a-z0-9][a-z0-9_-]{0,60})/(history/)?)?$", p)
        if not m:
            return False
        folder, hist = m.group(1), bool(m.group(2))
        folders = [d for d, _, _ in site_folders(self.root, load_config(self.root))]
        if folder and folder not in folders:
            return False
        scope = [folder] if folder else folders
        if not any(os.path.isdir(os.path.join(self.root, d)) and discover_page_files(self.root, d) for d in scope):
            return False
        gen = load_gen_index(self.root)
        if gen is None:
            return False
        if not folder:
            page = gen.root_html({d: gen.collect(d) for d in folders if d in gen.FOLDERS})
        elif hist:
            page = gen.history_html(folder, gen.collect(folder))
        else:
            page = gen.folder_html(folder, gen.collect(folder))
        data = page.encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True

    def _etag_json(self, obj):
        """200 with an ETag, or 304 when the browser's If-None-Match already has this body."""
        body = json.dumps(obj, ensure_ascii=False).encode()
        etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)

    def _page_target(self, method):
        """(rel, path, action) for a /_page/ request, or None. A PUT or POST names its action last."""
        rel = unquote(self._path())[len("/_page/"):].strip("/")
        action = None
        if method in PAGE_ACTIONS:
            rel, _, action = rel.rpartition("/")
        path = page_file(self.root, rel)
        return (rel, path, action) if path else None

    def _get_page(self):
        t = self._page_target("GET")
        if not t:
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        rel, path, _ = t
        cfg = load_config(self.root)
        doc = pagefile.load(path)
        self._note_taken(path, doc)
        doc = pagefile.load(path)
        route = page_route(cfg, rel.split("/")[0], doc)
        self._etag_json({"page": doc, "states": pagefile.item_states(doc), "summary": pagefile.summary(doc),
                         "route": route, "listening": is_listening(self.root, route["to"]), "diffs": page_diffs(doc)})

    def _note_taken(self, path, doc):
        """Record "picked up" for every sent submission an agent has moved to its inbox's taken/ folder."""
        for sub in doc.get("submissions", []):
            if sub.get("state") != "sent" or not sub.get("to") or not sub.get("file"):
                continue
            taken = os.path.join(self.root, "_inbox", sub["to"], "taken", sub["file"])
            if os.path.isfile(taken):
                at = dt.datetime.fromtimestamp(os.stat(taken).st_ctime).astimezone().isoformat(timespec="seconds")
                pagefile.mark_taken(path, sub["n"], at=at)

    def _get_index(self):
        cfg = load_config(self.root)
        folder = self._path()[len("/_index/"):].strip("/")
        folders = site_folders(self.root, cfg)
        gen = load_gen_index(self.root)
        if not folder:
            return self._etag_json({"title": cfg.get("title", ""), "folders": [
                {"id": d, "name": name, "blurb": blurb, "pages": folder_cards(self.root, d, gen)} for d, name, blurb in folders]})
        match = [f for f in folders if f[0] == folder]
        if not match or not os.path.isdir(os.path.join(self.root, folder)):
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        d, name, blurb = match[0]
        self._etag_json({"folder": d, "name": name, "blurb": blurb, "pages": folder_cards(self.root, d, gen)})

    def _get_save(self):
        name = self._save_name()
        fn = name and os.path.join(self.save_dir, name + ".json")
        if not fn or not os.path.isfile(fn):
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        with open(fn, "rb") as f:
            data = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Last-Modified", self.date_time_string(int(os.path.getmtime(fn))))
        self.end_headers()
        self.wfile.write(data)

    def _get_history(self):
        p = self._path()
        m = HIST_ENTRY_RE.match(p)
        if m:
            fn = os.path.join(self.save_dir, "history", m.group(1), m.group(2))
            if not os.path.isfile(fn):
                return self._plain(HTTPStatus.NOT_FOUND, "Not found")
            with open(fn, "rb") as f:
                data = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        m = HIST_LIST_RE.match(p)
        if not m:
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        key = m.group(1)
        hdir = os.path.join(self.save_dir, "history", key)
        rounds = []
        pages = discover_pages(self.root, load_config(self.root))
        src = ""
        if key in pages:
            try:
                src = open(pages[key]["path"], errors="ignore").read()
            except OSError:
                pass
        if os.path.isdir(hdir):
            for fn in sorted(os.listdir(hdir)):
                if not HIST_FILE_RE.match(fn):
                    continue
                try:
                    with open(os.path.join(hdir, fn)) as f:
                        entry = json.load(f)
                except (OSError, ValueError):
                    continue
                rounds.append({"file": fn, "round": entry.get("round"), "build": entry.get("build", ""),
                                "opened": entry.get("opened"), "closed": entry.get("closed"),
                                "count": _round_count(entry.get("answers") or {}, src)})
        rounds.sort(key=lambda r: r["round"] if isinstance(r["round"], int) else -1, reverse=True)
        page_removed = bool(rounds) and key not in pages
        self._json(HTTPStatus.OK, {"page_removed": page_removed, "rounds": rounds})

    def _json_body(self, limit):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise PermissionError("Content-Type must be application/json")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise LookupError("Content-Length required") from None
        if length < 0 or length > limit:
            raise OverflowError("Body too large")
        data = self.rfile.read(length)
        try:
            return data, json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("Body is not JSON") from None

    def _body_error(self, e):
        code = {PermissionError: HTTPStatus.UNSUPPORTED_MEDIA_TYPE, LookupError: HTTPStatus.LENGTH_REQUIRED,
                OverflowError: HTTPStatus.REQUEST_ENTITY_TOO_LARGE}.get(type(e), HTTPStatus.BAD_REQUEST)
        self._plain(code, str(e))

    def do_PUT(self):
        if self._path().startswith("/_page/"):
            return self._page_write("PUT")
        name = self._save_name()
        if not name:
            return self._plain(HTTPStatus.METHOD_NOT_ALLOWED, "Only /_save/<name>.json is writable")
        try:
            data, _ = self._json_body(MAX_BODY)
        except (PermissionError, LookupError, OverflowError, ValueError) as e:
            return self._body_error(e)
        os.makedirs(self.save_dir, exist_ok=True)
        fn = os.path.join(self.save_dir, name + ".json")
        prev = None
        if os.path.isfile(fn):
            try:
                with open(fn, "rb") as f:
                    prev = json.loads(f.read())
            except (OSError, ValueError):
                prev = None
        try:
            atomic_write(fn, data)
        except OSError:
            self.log_error("save failed for %s", name)
            return self._plain(HTTPStatus.INTERNAL_SERVER_ERROR, "Save failed")
        self.log_message("saved %s (%d bytes)", name, len(data))
        with ROUND_LOCK:
            try:
                self._check_round(name, prev)
            except Exception as e:
                self.log_error("round check failed for %s: %s", name, e)
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_POST(self):
        p = self._path()
        if p == "/_round-close":
            return self._do_round_close()
        if p.startswith("/_page/"):
            return self._page_write("POST")
        if p != "/_stale":
            return self._not_allowed()
        try:
            _, req = self._json_body(4096)
            folder, page = req["folder"], req["page"]
            if not isinstance(folder, str) or not isinstance(page, str):
                raise ValueError("folder and page must be strings")
        except (PermissionError, LookupError, OverflowError, ValueError) as e:
            return self._body_error(e)
        except (KeyError, TypeError):
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "Body must be JSON {folder, page}"})
        with STALE_LOCK:
            if FOLDER_RE.match(folder) and page_file(self.root, f"{folder}/{page}"):
                code, out = self._stale_page(folder, page)
            else:
                code, out = self._stale(folder, page)
        self.log_message("stale %s/%s -> %d %s", folder, page, code, out.get("error", out.get("deleted", "")))
        self._json(code, out)

    def _do_round_close(self):
        try:
            _, req = self._json_body(4096)
            name = req.get("name")
            if not _valid_save_name(name):
                raise ValueError("name must be a valid /_save/ page key")
        except (PermissionError, LookupError, OverflowError, ValueError) as e:
            return self._body_error(e)
        except (KeyError, TypeError):
            return self._json(HTTPStatus.BAD_REQUEST, {"error": "Body must be JSON {name}"})
        results_text = req.get("results_text") if isinstance(req.get("results_text"), str) else None
        with ROUND_LOCK:
            code, out = self._round_close(name, results_text)
        self.log_message("round-close %s -> %d %s", name, code, out.get("error", out.get("file", "")))
        self._json(code, out)

    def _not_allowed(self):
        self._plain(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed")

    do_DELETE = do_PATCH = _not_allowed

    def _stale(self, folder, page):
        cfg = load_config(self.root)
        if not FOLDER_RE.match(folder):
            return HTTPStatus.BAD_REQUEST, {"error": "Bad folder"}
        mpath = os.path.join(self.root, folder, "_status.json")
        try:
            with open(mpath) as f:
                manifest = json.load(f)
        except (OSError, ValueError):
            return HTTPStatus.NOT_FOUND, {"error": "No _status.json in that folder"}
        if page not in manifest or page == "review/":
            return HTTPStatus.NOT_FOUND, {"error": "Page not in the folder's _status.json"}
        if f"{folder}/{page}" in cfg.get("protected", []):
            return HTTPStatus.FORBIDDEN, {"error": "That page is a live checklist; it can't be marked stale"}
        if manifest[page].get("state") == "done":
            return HTTPStatus.CONFLICT, {"error": "Already done"}
        target = page_path(self.root, folder, page)
        if not target:
            return HTTPStatus.NOT_FOUND, {"error": "Page file not found inside that folder"}
        if os.path.isdir(target):
            shutil.rmtree(target)
        else:
            os.remove(target)
        when = now_local(cfg)
        who = cfg.get("owner", "owner")
        manifest[page]["state"] = "done"
        manifest[page]["note"] = f"Stale ({who}, {when:%Y-%m-%d %H:%M} {cfg.get('tz_label', when.tzname())})"
        atomic_write(mpath, (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode())
        entry = {"at": when.isoformat(timespec="seconds"), "folder": folder, "page": page, "by": who,
                 "deleted": os.path.relpath(target, self.root)}
        append_log(self.save_dir, "stale-log.json", entry)
        warnings = []
        builder = cfg.get("builders", {}).get(folder)
        steps = [[sys.executable, os.path.normpath(os.path.join(self.root, builder))] if builder else
                 [sys.executable, os.path.join(self.root, "_site", "build-review.py"), folder],
                 [sys.executable, os.path.join(self.root, "gen-index.py")]]
        for cmd in steps:
            if not os.path.exists(cmd[1]):
                continue
            r = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, timeout=120)
            if r.returncode:
                warnings.append(f"{os.path.basename(cmd[1])} exited {r.returncode}")
                self.log_error("%s failed: %s", cmd[1], (r.stderr or r.stdout).strip()[-400:])
        return HTTPStatus.OK, {"deleted": entry["deleted"], "warnings": warnings}

    def _page_write(self, method):
        t = self._page_target(method)
        if t and t[2] not in PAGE_ACTIONS[method]:
            return self._plain(HTTPStatus.METHOD_NOT_ALLOWED, "Unknown page action")
        if not t:
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        rel, path, action = t
        try:
            _, req = self._json_body(MAX_BODY)
            if not isinstance(req, dict):
                raise ValueError("Body must be a JSON object")
        except (PermissionError, LookupError, OverflowError, ValueError) as e:
            return self._body_error(e)
        cfg = load_config(self.root)
        try:
            out = getattr(self, "_page_" + action)(rel, path, req, cfg)
        except pagefile.PageError as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"errors": e.errors})
        except (TypeError, ValueError, AttributeError) as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"errors": [str(e)]})
        if isinstance(out, tuple):
            return self._json(*out)
        self.log_message("page %s %s -> %s", action, rel, out)
        self._json(HTTPStatus.OK, out)

    def _page_answers(self, rel, path, req, cfg):
        answers = req.get("answers")
        if not isinstance(answers, dict) or not all(isinstance(a, dict) for a in answers.values()):
            raise ValueError("answers must be an object of {answer, note} by item id")
        when = now_local(cfg).isoformat(timespec="seconds")
        return {"rev": pagefile.save_answers(path, answers, by=cfg.get("owner", "owner"), base=req.get("base"), now=when)}

    def _page_round(self, rel, path, req, cfg):
        results = req.get("results") if isinstance(req.get("results"), str) else None
        return {"round": pagefile.new_round(path, results=results, now=now_local(cfg).isoformat(timespec="seconds"))}

    def _page_restart(self, rel, path, req, cfg):
        checkpoint = req.get("checkpoint")
        if not isinstance(checkpoint, str):
            raise ValueError("checkpoint must be a string")
        results = req.get("results") if isinstance(req.get("results"), str) else None
        when = now_local(cfg)
        n = pagefile.restart(path, checkpoint, by=cfg.get("owner", "owner"), results=results, now=when.isoformat(timespec="seconds"))
        out = self._submit(rel, path, cfg, "restart", [], results or f"Restart from {checkpoint}", when)
        if isinstance(out, tuple):
            return out
        return {"round": n, **out}

    def _page_unlock(self, rel, path, req, cfg):
        return {"rev": pagefile.release(path)}

    def _page_send(self, rel, path, req, cfg):
        kind = req.get("kind")
        if kind not in ("send", "blocker"):
            raise ValueError("kind must be send or blocker")
        doc = pagefile.load(path)
        ids = {it["id"] for it in doc["items"]}
        items = req.get("items")
        if items is None:
            items = [i for i in doc["rounds"][-1]["answers"] if i in ids]
        if not isinstance(items, list) or any(i not in ids for i in items):
            raise ValueError("items must be ids of items on this page")
        if kind == "blocker" and len(items) != 1:
            raise ValueError("a blocker sends exactly one item")
        results = req.get("results") if isinstance(req.get("results"), str) else ""
        return self._submit(rel, path, cfg, kind, items, results, now_local(cfg))

    def _submit(self, rel, path, cfg, kind, items, results, when):
        """Record the submission on the page, then write it to the route's inbox atomically."""
        doc = pagefile.load(path)
        route = page_route(cfg, rel.split("/")[0], doc)
        if route["mode"] == "copy":
            return HTTPStatus.CONFLICT, {"error": "This page copies its results; it doesn't send them"}
        sub = pagefile.add_submission(path, {"kind": kind, "to": route["to"], "items": items,
                                             "file": submission_name(kind, rel, when)}, now=when.isoformat(timespec="seconds"))
        doc = pagefile.load(path)
        answers = doc["rounds"][-1]["answers"]
        pos = {it["id"]: n for n, it in enumerate(doc["items"], 1)}
        host = cfg.get("host", "127.0.0.1")
        port = self.server.server_address[1] if self.server else cfg.get("port", 8000)
        payload = {"schema": "handoff.submission/v1", "n": sub["n"], "kind": kind, "page": rel,
                   "url": f"http://{host}:{port}/{rel}", "title": doc["title"], "build": doc.get("build"),
                   "round": sub["round"], "rev": sub["rev"], "at": sub["at"],
                   "items": [{"id": i, "n": pos[i], "answer": (answers.get(i) or {}).get("answer", ""),
                              "note": (answers.get(i) or {}).get("note", ""), "blocker": kind == "blocker"} for i in items],
                   "results": results}
        idir = os.path.join(self.root, "_inbox", route["to"])
        try:
            os.makedirs(idir, exist_ok=True)
            atomic_write(os.path.join(idir, sub["file"]), (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode())
        except OSError as e:
            self.log_error("inbox write failed for %s: %s", rel, e)
            pagefile.mark_undelivered(path, sub["n"])
            return HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"It didn't reach {route['to']}'s inbox"}
        if kind == "send":
            pagefile.hold(path, sub["n"])
        return {"n": sub["n"], "file": sub["file"], "to": route["to"], "listening": is_listening(self.root, route["to"])}

    def _stale_page(self, folder, page):
        """Stale on a page file: mark it done (kept in the file) and move it to <folder>/_old/."""
        cfg = load_config(self.root)
        rel = f"{folder}/{page}"
        path = page_file(self.root, rel)
        if rel in cfg.get("protected", []):
            return HTTPStatus.FORBIDDEN, {"error": "That page is a live checklist; it can't be marked stale"}
        doc = pagefile.load(path)
        st = doc.get("status") or {}
        if st.get("state") == "done":
            return HTTPStatus.CONFLICT, {"error": "Already done"}
        when = now_local(cfg)
        who = cfg.get("owner", "owner")
        note = f"Stale ({who}, {when:%Y-%m-%d %H:%M} {cfg.get('tz_label', when.tzname())})"
        pagefile.set_status(path, "done", note=note, chips=st.get("chips"), priority=st.get("priority"))
        dest_dir = os.path.join(self.root, folder, "_old", *page.split("/")[:-1])
        os.makedirs(dest_dir, exist_ok=True)
        base = os.path.join(dest_dir, page.split("/")[-1])
        dest, i = base + ".json", 1
        while os.path.exists(dest):
            dest, i = f"{base}-{i}.json", i + 1
        os.replace(path, dest)
        if os.path.exists(path + ".lock"):
            os.replace(path + ".lock", dest + ".lock")
        moved = os.path.relpath(dest, self.root).replace(os.sep, "/")
        append_log(self.save_dir, "stale-log.json", {"at": when.isoformat(timespec="seconds"), "folder": folder,
                                                     "page": page, "by": who, "moved": moved})
        return HTTPStatus.OK, {"moved": moved, "warnings": []}

    def _round_meta_path(self, name):
        return os.path.join(self.save_dir, "_round-meta", name + ".json")

    def _read_round_meta(self, name):
        try:
            with open(self._round_meta_path(name)) as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _write_round_meta(self, name, meta):
        p = self._round_meta_path(name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        atomic_write(p, (json.dumps(meta) + "\n").encode())

    def _write_history_entry(self, name, entry, closed_at, label_source):
        hdir = os.path.join(self.save_dir, "history", name)
        os.makedirs(hdir, exist_ok=True)
        base = closed_at.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
        label = _slug(label_source)
        i = 0
        while True:
            stamp = base if i == 0 else f"{base}-{i}"
            fn = os.path.join(hdir, f"{stamp}Z__{label}.json")
            if not os.path.exists(fn):
                break
            i += 1
        atomic_write(fn, (json.dumps(entry, indent=2, ensure_ascii=False) + "\n").encode())
        return fn

    def _check_round(self, name, prev):
        """Called after every successful /_save/ PUT: archive the previous round when the page's
        data-build or data-review-reset changed since the last PUT for it."""
        cfg = load_config(self.root)
        info = discover_pages(self.root, cfg).get(name)
        if not info:
            return
        try:
            src = open(info["path"], errors="ignore").read()
        except OSError:
            return
        attrs = _body_attrs(src)
        new_sig = (attrs.get("data-build", ""), attrs.get("data-review-reset", ""))
        meta = self._read_round_meta(name)
        now = now_local(cfg)
        if meta is None:
            self._write_round_meta(name, {"round": 1, "build": new_sig[0], "reset": new_sig[1],
                                           "opened": now.isoformat(timespec="seconds")})
            return
        if (meta.get("build", ""), meta.get("reset", "")) == new_sig:
            return
        title = _page_title(src, info["page"])
        answers = prev or {}
        results_text = _results_text(info["page"], title, src, attrs, answers, meta["round"], meta.get("build", ""))
        entry = {"page": info["page"], "title": title, "round": meta["round"], "build": meta.get("build", ""),
                 "opened": meta.get("opened", now.isoformat(timespec="seconds")),
                 "closed": now.isoformat(timespec="seconds"), "answers": answers, "results_text": results_text}
        fn = self._write_history_entry(name, entry, now, meta.get("build") or meta.get("reset", ""))
        self._write_round_meta(name, {"round": meta["round"] + 1, "build": new_sig[0], "reset": new_sig[1],
                                       "opened": now.isoformat(timespec="seconds")})
        self.log_message("archived round %s for %s -> %s", meta["round"], name, os.path.basename(fn))

    def _round_close(self, name, results_override):
        """POST /_round-close: archive the current round by hand, regardless of whether
        data-build or data-review-reset changed, then open the next round under the same build."""
        cfg = load_config(self.root)
        info = discover_pages(self.root, cfg).get(name)
        if not info:
            return HTTPStatus.NOT_FOUND, {"error": "Not a known page"}
        fn = os.path.join(self.save_dir, name + ".json")
        if not os.path.isfile(fn):
            return HTTPStatus.NOT_FOUND, {"error": "Nothing saved for this page yet"}
        try:
            with open(fn, "rb") as f:
                answers = json.loads(f.read())
        except ValueError:
            answers = {}
        try:
            src = open(info["path"], errors="ignore").read()
        except OSError:
            src = ""
        attrs = _body_attrs(src)
        now = now_local(cfg)
        meta = self._read_round_meta(name) or {"round": 1, "build": attrs.get("data-build", ""),
                                                "reset": attrs.get("data-review-reset", ""),
                                                "opened": now.isoformat(timespec="seconds")}
        title = _page_title(src, info["page"])
        results_text = results_override.strip() if results_override and results_override.strip() else \
            _results_text(info["page"], title, src, attrs, answers, meta["round"], meta.get("build", ""))
        entry = {"page": info["page"], "title": title, "round": meta["round"], "build": meta.get("build", ""),
                 "opened": meta.get("opened", now.isoformat(timespec="seconds")),
                 "closed": now.isoformat(timespec="seconds"), "answers": answers, "results_text": results_text}
        hist_fn = self._write_history_entry(name, entry, now, meta.get("build") or meta.get("reset", ""))
        self._write_round_meta(name, {"round": meta["round"] + 1, "build": meta.get("build", ""),
                                       "reset": meta.get("reset", ""), "opened": now.isoformat(timespec="seconds")})
        return HTTPStatus.OK, {"round": meta["round"], "file": os.path.basename(hist_fn)}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("port", type=int, nargs="?")
    ap.add_argument("--bind")
    ap.add_argument("--directory", default=os.getcwd())
    a = ap.parse_args()
    root = os.path.abspath(a.directory)
    cfg = load_config(root)
    a.port = a.port or int(cfg.get("port", 8000))
    a.bind = a.bind or cfg.get("host", "127.0.0.1")
    repo = in_git_work_tree(root)
    if repo:
        sys.exit(f"Refusing to serve {root}: it is inside the git work tree at {repo}. "
                 "The site's folder is working memory and is never committed; copy the template elsewhere.")
    Handler.root = root
    Handler.save_dir = os.path.join(root, "_saved")
    threading.Thread(target=pruner, args=(root, Handler.save_dir), daemon=True).start()
    handler = functools.partial(Handler, directory=root)
    with ThreadingHTTPServer((a.bind, a.port), handler) as httpd:
        print(f"Serving {root} on http://{a.bind}:{a.port}/ (saves in {Handler.save_dir})", file=sys.stderr, flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()

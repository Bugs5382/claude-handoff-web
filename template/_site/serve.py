#!/usr/bin/env python3
"""Static file server for the hand-off site, plus a tiny JSON save store.

Serves a directory exactly like `python3 -m http.server`, and adds:
  PUT  /_save/<name>.json  store a JSON body (max 256 KB) in <root>/_saved/<name>.json, atomically; 204
  GET  /_save/<name>.json  return it, or 404
  POST /_stale             {"folder": "...", "page": "..."}: delete a needs-you page listed in that folder's
                           _status.json, mark it done there, rebuild the indexes, log it in _saved/stale-log.json
Nothing else is writable, and <root>/_saved/ is never served directly.
Files under any _old/ folder older than prune_old_days are deleted hourly (logged in _saved/prune-log.json).
The served folder is working memory: the server refuses to start inside a git work tree.

Settings come from <root>/site.json (all optional here):
  {"owner": "<owner>", "host": "127.0.0.1", "port": 8000, "timezone": "UTC", "tz_label": "UTC",
   "protected": ["folder/page/"], "builders": {"folder": "../its-own-builder.py"},
   "prune_old": true, "prune_old_days": 7}
Command-line flags override host and port.
"""
import argparse
import datetime as dt
import functools
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

MAX_BODY = 256 * 1024
SAVE_RE = re.compile(r"^/_save/([a-z0-9._-]{1,120})\.json$")
FOLDER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,60}$")
RESERVED = {"stale-log", "prune-log"}
STALE_LOCK = threading.Lock()


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


class Handler(SimpleHTTPRequestHandler):
    save_dir = ""
    root = ""
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".md": "text/plain; charset=utf-8"}

    def _path(self):
        return urlsplit(self.path).path

    def end_headers(self):
        p = self._path()
        if p.startswith("/_save/") or p.startswith("/_stale") or p.endswith(".html") or p.endswith("/"):
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
        return p == "/_saved" or p.startswith("/_saved/")

    def do_GET(self):
        if self._path().startswith("/_save/"):
            return self._get_save()
        if self._blocked():
            return self._plain(HTTPStatus.NOT_FOUND, "Not found")
        return super().do_GET()

    def do_HEAD(self):
        if self._path().startswith("/_save/") or self._blocked():
            return self._plain(HTTPStatus.NOT_FOUND)
        return super().do_HEAD()

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
        name = self._save_name()
        if not name:
            return self._plain(HTTPStatus.METHOD_NOT_ALLOWED, "Only /_save/<name>.json is writable")
        try:
            data, _ = self._json_body(MAX_BODY)
        except (PermissionError, LookupError, OverflowError, ValueError) as e:
            return self._body_error(e)
        os.makedirs(self.save_dir, exist_ok=True)
        try:
            atomic_write(os.path.join(self.save_dir, name + ".json"), data)
        except OSError:
            self.log_error("save failed for %s", name)
            return self._plain(HTTPStatus.INTERNAL_SERVER_ERROR, "Save failed")
        self.log_message("saved %s (%d bytes)", name, len(data))
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_POST(self):
        if self._path() != "/_stale":
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
            code, out = self._stale(folder, page)
        self.log_message("stale %s/%s -> %d %s", folder, page, code, out.get("error", out.get("deleted", "")))
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

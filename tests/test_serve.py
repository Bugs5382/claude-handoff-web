"""End-to-end tests for template/_site/serve.py: a real server on a free port in a temp folder."""

import http.client
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SERVE = ROOT / "template" / "_site" / "serve.py"


def load_serve():
    spec = importlib.util.spec_from_file_location("serve", SERVE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def request(url, method="GET", body=None, ctype="application/json"):
    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, method=method)
    if ctype and data is not None:
        req.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


@pytest.fixture()
def site(tmp_path):
    root = tmp_path / "site"
    shutil.copytree(ROOT / "template", root)
    for d in ("demo", "guide"):
        shutil.copytree(ROOT / "example" / d, root / d)
    shutil.copy(ROOT / "example" / "site.json", root / "site.json")
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(root / "_site" / "serve.py"), str(port), "--bind", "127.0.0.1",
                             "--directory", str(root)], stderr=subprocess.PIPE)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/", timeout=1)
            break
        except OSError:
            time.sleep(0.05)
    yield root, base
    proc.terminate()
    proc.wait(timeout=5)


def test_static_and_cache_headers(site):
    _, base = site
    status, _, headers = request(base + "/demo/design-review.html")
    assert status == 200
    assert headers.get("Cache-Control") == "no-store"
    status, _, headers = request(base + "/_site/site.css")
    assert status == 200
    assert "Cache-Control" not in headers


def test_save_round_trip(site):
    root, base = site
    assert request(base + "/_save/review-demo.json")[0] == 404
    assert request(base + "/_save/review-demo.json", "PUT", '{"s1": {"v": "yes", "n": ""}}')[0] == 204
    status, body, headers = request(base + "/_save/review-demo.json")
    assert status == 200
    assert json.loads(body) == {"s1": {"v": "yes", "n": ""}}
    assert headers.get("Cache-Control") == "no-store"
    assert (root / "_saved" / "review-demo.json").exists()


@pytest.mark.parametrize(
    ("path", "body", "ctype", "code"),
    [
        ("/_save/Bad.json", "{}", "application/json", 405),
        ("/_save/x.json", "not json", "application/json", 400),
        ("/_save/x.json", "{}", "text/plain", 415),
        ("/_save/stale-log.json", "{}", "application/json", 405),
        ("/demo/x.json", "{}", "application/json", 405),
    ],
    ids=["bad-name", "not-json", "wrong-type", "reserved-name", "outside-save"],
)
def test_save_rejects(site, path, body, ctype, code):
    _, base = site
    assert request(base + path, "PUT", body, ctype)[0] == code


def test_save_rejects_oversized_body(site):
    _, base = site
    conn = http.client.HTTPConnection(base.removeprefix("http://"), timeout=10)
    conn.putrequest("PUT", "/_save/x.json")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(256 * 1024 + 1))
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_saved_folder_never_served(site):
    _, base = site
    request(base + "/_save/x.json", "PUT", "{}")
    for p in ("/_saved/", "/_saved/x.json", "/_site/../_saved/x.json", "/%5Fsaved/x.json"):
        assert request(base + p)[0] == 404, p


def test_stale_deletes_and_marks_done(site):
    root, base = site
    status, body, _ = request(base + "/_stale", "POST", json.dumps({"folder": "demo", "page": "design-review.html"}))
    assert status == 200, body
    assert not (root / "demo" / "design-review.html").exists()
    entry = json.loads((root / "demo" / "_status.json").read_text())["design-review.html"]
    assert entry["state"] == "done"
    assert entry["note"].startswith("Stale (Alex, ")
    log = (root / "_saved" / "stale-log.json").read_text().splitlines()
    assert json.loads(log[-1])["page"] == "design-review.html"
    assert (root / "demo" / "signoff-checklist.html").exists()
    unified = (root / "demo" / "review" / "index.html").read_text()
    assert 'data-src="design-review.html"' not in unified
    assert 'data-review-stale="design-review.html"' in unified


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"folder": "demo", "page": "review/"}, 404),
        ({"folder": "demo", "page": "missing.html"}, 404),
        ({"folder": "_site", "page": "review.js"}, 400),
        ({"folder": "../x", "page": "a.html"}, 400),
        ({"folder": "demo"}, 400),
    ],
)
def test_stale_rejects(site, payload, code):
    _, base = site
    assert request(base + "/_stale", "POST", json.dumps(payload))[0] == code


def test_stale_refuses_protected(site):
    root, base = site
    cfg = json.loads((root / "site.json").read_text())
    cfg["protected"] = ["demo/signoff-checklist.html"]
    (root / "site.json").write_text(json.dumps(cfg))
    status, _, _ = request(base + "/_stale", "POST", json.dumps({"folder": "demo", "page": "signoff-checklist.html"}))
    assert status == 403
    assert (root / "demo" / "signoff-checklist.html").exists()


def test_page_path_rejects_escapes(tmp_path):
    serve = load_serve()
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "a.html").write_text("x")
    (tmp_path / "site.json").write_text("{}")
    assert serve.page_path(str(tmp_path), "demo", "a.html") == str(tmp_path / "demo" / "a.html")
    for bad in ("../site.json", "_old/a.html", "index.html", "review/", "a.html/", "/etc/passwd", "", ".hidden",
                "x/../../site.json"):
        assert serve.page_path(str(tmp_path), "demo", bad) is None, bad


def test_prune_old_removes_only_old_files(tmp_path):
    serve = load_serve()
    old = tmp_path / "demo" / "_old"
    old.mkdir(parents=True)
    (old / "stale.html").write_text("x")
    (old / "fresh.html").write_text("x")
    (tmp_path / "demo" / "page.html").write_text("x")
    past = time.time() - 9 * 86400
    os.utime(old / "stale.html", (past, past))
    os.utime(tmp_path / "demo" / "page.html", (past, past))
    removed = serve.prune_old(str(tmp_path), str(tmp_path / "_saved"), 7)
    assert removed == [os.path.join("demo", "_old", "stale.html")]
    assert (old / "fresh.html").exists()
    assert (tmp_path / "demo" / "page.html").exists()
    assert "stale.html" in (tmp_path / "_saved" / "prune-log.json").read_text()


def test_refuses_to_serve_inside_git_work_tree(tmp_path):
    (tmp_path / ".git").mkdir()
    site = tmp_path / "site"
    site.mkdir()
    r = subprocess.run([sys.executable, str(SERVE), str(free_port()), "--directory", str(site)],
                       capture_output=True, text=True, timeout=10)
    assert r.returncode != 0
    assert "git work tree" in r.stderr

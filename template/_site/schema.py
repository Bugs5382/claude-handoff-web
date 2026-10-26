#!/usr/bin/env python3
"""Validator for handoff.page/v1 page files, standard library only.

validate(doc) returns a list of errors, each "<path>: <what was expected>", and an empty list for a valid page.
Items are addressed by id (items[c1].steps); anything without a usable id, and every other list, by position
counted from 1 (body[#2]).

Usage: schema.py PAGE.json    (prints the errors; exit 1 when there are any)
       from schema import validate
"""
import json
import re
import sys

SCHEMA = "handoff.page/v1"
KINDS = ("review", "checklist", "journey", "backlog", "questions", "reference", "status")
DEFAULT_TYPE = {"review": "section", "checklist": "check", "journey": "step", "backlog": "choice",
                "questions": "question", "reference": "info", "status": "info"}
ANSWERS = ("yes", "no", "changes", "skipped")
TYPE_ANSWERS = {"section": ANSWERS[:3], "screen": ANSWERS[:3], "contract": ANSWERS[:3], "diff": ANSWERS[:3],
                "check": ANSWERS, "step": ANSWERS}
STATES = ("needs-you", "reference", "done")
MODES = ("send", "copy", "both")
ACTIONS = ("filed", "fixed", "reopen", "unblock", "wontfix", "info")
TONES = ("info", "warn", "ok", "danger")
SUBMISSION_KINDS = ("send", "blocker", "restart")
SUBMISSION_STATES = ("sent", "taken")
BLOCKS = ("p", "list", "olist", "code", "image", "table", "diff", "copy", "note", "html")
BLOCK_EXTRAS = {"code": ("lang",), "image": ("alt", "caption"), "note": ("tone",)}

ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,40}\Z")
AGENT = re.compile(r"[a-z0-9][a-z0-9_-]{0,40}\Z")
ID_RULE = "expected a-z, 0-9, _ and -, starting with a letter or digit, up to 41 characters"

TOP = ("schema", "rev", "kind", "title", "summary", "build", "reset", "status", "route", "options", "items",
       "rounds", "thread", "submissions")
COMMON = ("id", "type", "title", "section", "body")
ANSWERABLE = ("answers", "skip", "dependsOn", "blockedBy")
TYPE_FIELDS = {
    "section": ANSWERABLE,
    "check": ANSWERABLE + ("howto",),
    "step": ANSWERABLE + ("steps", "checkpoint", "howto"),
    "screen": ANSWERABLE + ("images", "fields"),
    "contract": ANSWERABLE + ("fields", "forms"),
    "diff": ANSWERABLE + ("old", "new", "code"),
    "question": ("suggested",),
    "choice": ("blockedBy",),
    "info": (),
}


class _V:
    def __init__(self):
        self.errors = []

    def err(self, path, msg):
        self.errors.append(f"{path}: {msg}")

    def keys(self, obj, path, allowed, required=()):
        for k in obj:
            if k not in allowed:
                self.err(_join(path, k), "unknown key")
        for k in required:
            if k not in obj:
                self.err(_join(path, k), "required")

    def string(self, obj, key, path, required=False, nullable=False):
        if key not in obj:
            if required:
                self.err(_join(path, key), "required")
            return
        v = obj[key]
        if v is None and nullable:
            return
        if not isinstance(v, str):
            self.err(_join(path, key), "expected a string")
        elif required and not v.strip():
            self.err(_join(path, key), "must not be empty")

    def integer(self, obj, key, path, nullable=False, minimum=None):
        if key not in obj or (obj[key] is None and nullable):
            return
        v = obj[key]
        if not isinstance(v, int) or isinstance(v, bool):
            self.err(_join(path, key), "expected an integer")
        elif minimum is not None and v < minimum:
            self.err(_join(path, key), f"expected {minimum} or more")

    def strings(self, obj, key, path):
        if key in obj and not _strlist(obj[key]):
            self.err(_join(path, key), "expected a list of strings")

    def choice(self, obj, key, path, values):
        if key in obj and obj[key] not in values:
            self.err(_join(path, key), "expected one of " + ", ".join(values))


def _join(path, key):
    return f"{path}.{key}" if path else key


def _strlist(v):
    return isinstance(v, list) and all(isinstance(s, str) for s in v)


def _picture(src):
    return isinstance(src, str) and src.strip() != "" and not src.startswith("data:") and ".." not in src.split("/")


def validate(doc):
    """Every problem with a handoff.page/v1 document, as "<path>: <what was expected>"."""
    v = _V()
    if not isinstance(doc, dict):
        return ["(page): expected a JSON object"]
    v.keys(doc, "", TOP, ("schema", "kind", "title", "items"))
    if "schema" in doc and doc["schema"] != SCHEMA:
        v.err("schema", f"expected {SCHEMA}")
    v.integer(doc, "rev", "", minimum=0)
    v.choice(doc, "kind", "", KINDS)
    kind = doc.get("kind") if doc.get("kind") in KINDS else "review"
    v.string(doc, "title", "", required="title" in doc)
    v.string(doc, "summary", "")
    v.string(doc, "build", "", nullable=True)
    v.integer(doc, "reset", "", nullable=True, minimum=0)
    if kind == "checklist" and not doc.get("build"):
        v.err("build", "required on a checklist")
    _status(v, doc.get("status"))
    _route(v, doc.get("route"))
    choices = _options(v, doc, kind)
    _items(v, doc.get("items"), kind, choices)
    _rounds(v, doc.get("rounds"))
    _thread(v, doc.get("thread"))
    _submissions(v, doc.get("submissions"))
    return v.errors


def _status(v, st):
    if st is None:
        return
    if not isinstance(st, dict):
        v.err("status", "expected an object")
        return
    v.keys(st, "status", ("state", "note", "chips", "priority"), ("state",))
    v.choice(st, "state", "status", STATES)
    v.string(st, "note", "status")
    v.strings(st, "chips", "status")
    v.integer(st, "priority", "status")


def _route(v, rt):
    if rt is None:
        return
    if not isinstance(rt, dict):
        v.err("route", "expected an object")
        return
    v.keys(rt, "route", ("to", "mode"), ("to", "mode"))
    if "to" in rt and not (isinstance(rt["to"], str) and AGENT.match(rt["to"])):
        v.err("route.to", "expected an agent name like ops or app")
    v.choice(rt, "mode", "route", MODES)


def _options(v, doc, kind):
    opts = doc.get("options")
    if opts is None:
        if kind == "backlog":
            v.err("options", "required on a backlog")
        return ()
    if not isinstance(opts, dict):
        v.err("options", "expected an object with choices and default")
        return ()
    v.keys(opts, "options", ("choices", "default"), ("choices",))
    raw = opts.get("choices")
    if not isinstance(raw, list) or not raw:
        v.err("options.choices", "expected a list of {value, label}")
        return ()
    values = []
    for i, c in enumerate(raw, 1):
        p = f"options.choices[#{i}]"
        if not isinstance(c, dict):
            v.err(p, "expected an object")
            continue
        v.keys(c, p, ("value", "label"), ("value", "label"))
        v.string(c, "value", p)
        v.string(c, "label", p)
        if isinstance(c.get("value"), str):
            values.append(c["value"])
    if "default" in opts and opts["default"] not in values:
        v.err("options.default", "expected one of the choice values")
    return tuple(values)


def _items(v, items, kind, choices):
    if items is None:
        return set()
    if not isinstance(items, list):
        v.err("items", "expected a list of items")
        return set()
    seen = set()
    named = []
    for i, it in enumerate(items, 1):
        if not isinstance(it, dict):
            v.err(f"items[#{i}]", "expected an object")
            continue
        iid = it.get("id")
        good = isinstance(iid, str) and bool(ID.match(iid))
        p = f"items[{iid}]" if good else f"items[#{i}]"
        if "id" not in it:
            v.err(_join(p, "id"), "required")
        elif not good:
            v.err(_join(p, "id"), ID_RULE)
        elif iid in seen:
            v.err(_join(p, "id"), "duplicate id")
        else:
            seen.add(iid)
        named.append((p, it))
        _item(v, it, p, kind, choices)
    for p, it in named:
        deps = it.get("dependsOn")
        if not _strlist(deps):
            continue
        for d in deps:
            if d == it.get("id"):
                v.err(_join(p, "dependsOn"), f"{d} depends on itself")
            elif d not in seen:
                v.err(_join(p, "dependsOn"), f"no item {d} on this page")
    return seen


def _item(v, it, p, kind, choices):
    typ = it.get("type", DEFAULT_TYPE[kind])
    if typ not in TYPE_FIELDS:
        v.err(_join(p, "type"), "expected one of " + ", ".join(TYPE_FIELDS))
        return
    if kind in ("reference", "status") and typ != "info":
        v.err(_join(p, "type"), f"a {kind} page holds info items only")
    if typ == "choice" and not choices:
        v.err(_join(p, "type"), "a choice item needs the page's options")
    allowed = COMMON + TYPE_FIELDS[typ]
    for k in it:
        if k not in allowed:
            known = any(k in f for f in TYPE_FIELDS.values())
            v.err(_join(p, k), f"not allowed on a {typ} item" if known else "unknown key")
    v.string(it, "title", p, required=True)
    v.string(it, "section", p)
    _blocks(v, it, "body", p)
    _blocks(v, it, "howto", p)
    if "answers" in it:
        a = it["answers"]
        if not _strlist(a) or not a or any(x not in ANSWERS for x in a):
            v.err(_join(p, "answers"), "expected values from " + ", ".join(ANSWERS))
    if "skip" in it and not isinstance(it["skip"], bool):
        v.err(_join(p, "skip"), "expected true or false")
    v.strings(it, "dependsOn", p)
    v.string(it, "blockedBy", p)
    v.strings(it, "steps", p)
    v.string(it, "checkpoint", p)
    v.string(it, "suggested", p)
    if typ == "diff":
        v.string(it, "old", p, required=True)
        if "new" not in it:
            v.err(_join(p, "new"), "required")
        else:
            v.string(it, "new", p)
        if "code" in it and not isinstance(it["code"], bool):
            v.err(_join(p, "code"), "expected true or false")
    if "images" in it:
        _images(v, it["images"], _join(p, "images"))
    if "fields" in it:
        _fields(v, it["fields"], _join(p, "fields"))
    if "forms" in it:
        forms = it["forms"]
        if not isinstance(forms, list):
            v.err(_join(p, "forms"), "expected a list of forms")
        else:
            for i, f in enumerate(forms, 1):
                fp = f"{p}.forms[#{i}]"
                if not isinstance(f, dict):
                    v.err(fp, "expected an object")
                    continue
                v.keys(f, fp, ("name", "fields"))
                v.string(f, "name", fp, required=True)
                if "fields" in f:
                    _fields(v, f["fields"], _join(fp, "fields"))


def _images(v, imgs, p):
    if not isinstance(imgs, list):
        v.err(p, "expected a list of {src, alt, caption}")
        return
    for i, im in enumerate(imgs, 1):
        ip = f"{p}[#{i}]"
        if not isinstance(im, dict):
            v.err(ip, "expected an object")
            continue
        v.keys(im, ip, ("src", "alt", "caption"), ("src",))
        if "src" in im and not _picture(im["src"]):
            v.err(_join(ip, "src"), "pictures are files next to the page, such as img/a.png")
        v.string(im, "alt", ip)
        v.string(im, "caption", ip)


def _fields(v, fields, p):
    if not isinstance(fields, list):
        v.err(p, "expected a list of {name, type, rule}")
        return
    for i, f in enumerate(fields, 1):
        fp = f"{p}[#{i}]"
        if not isinstance(f, dict):
            v.err(fp, "expected an object")
            continue
        v.keys(f, fp, ("name", "type", "rule"), ("name",))
        for k in ("name", "type", "rule"):
            v.string(f, k, fp)


def _blocks(v, it, key, p):
    if key not in it:
        return
    blocks = it[key]
    bp = _join(p, key)
    if not isinstance(blocks, list):
        v.err(bp, "expected a list of blocks")
        return
    for i, b in enumerate(blocks, 1):
        _block(v, b, f"{bp}[#{i}]")


def _block(v, b, p):
    names = [k for k in b if k in BLOCKS] if isinstance(b, dict) else []
    if len(names) != 1:
        v.err(p, "expected one block key: " + ", ".join(BLOCKS))
        return
    name = names[0]
    v.keys(b, p, (name,) + BLOCK_EXTRAS.get(name, ()))
    val = b[name]
    if name in ("p", "code", "copy", "note", "html"):
        v.string(b, name, p)
    elif name in ("list", "olist"):
        v.strings(b, name, p)
    elif name == "image":
        if not _picture(val):
            v.err(_join(p, "image"), "pictures are files next to the page, such as img/a.png")
    elif name == "table":
        if not isinstance(val, list) or not val or not all(_strlist(r) for r in val):
            v.err(_join(p, "table"), "expected a list of rows of strings")
        else:
            width = len(val[0])
            for i, row in enumerate(val[1:], 2):
                if len(row) != width:
                    v.err(f"{p}.table[#{i}]", f"expected {width} cells like the header")
    elif name == "diff":
        dp = _join(p, "diff")
        if not isinstance(val, dict):
            v.err(dp, "expected {old, new, code}")
        else:
            v.keys(val, dp, ("old", "new", "code"), ("old", "new"))
            v.string(val, "old", dp)
            v.string(val, "new", dp)
            if "code" in val and not isinstance(val["code"], bool):
                v.err(_join(dp, "code"), "expected true or false")
    for extra in BLOCK_EXTRAS.get(name, ()):
        v.string(b, extra, p)
    if name == "note":
        v.choice(b, "tone", p, TONES)


def _entry(v, a, p, history):
    if not isinstance(a, dict):
        v.err(p, "expected an object")
        return
    allowed = ("answer", "note", "by", "at") + (() if history else ("hash", "was"))
    v.keys(a, p, allowed, ("answer", "at"))
    for k in ("answer", "note", "by", "at", "hash"):
        v.string(a, k, p)
    if not history and "was" in a:
        if not isinstance(a["was"], list):
            v.err(_join(p, "was"), "expected a list of earlier answers")
        else:
            for i, w in enumerate(a["was"], 1):
                _entry(v, w, f"{p}.was[#{i}]", True)


def _strmap(v, m, p):
    if not isinstance(m, dict) or not all(isinstance(x, str) for x in m.values()):
        v.err(p, "expected an object of strings")


def _rounds(v, rounds):
    if rounds is None:
        return
    if not isinstance(rounds, list) or not rounds:
        v.err("rounds", "expected a list of rounds")
        return
    keys = ("round", "build", "reset", "opened", "closed", "openedBy", "answers", "checkpoints", "reopened",
            "results", "restart")
    for i, r in enumerate(rounds, 1):
        p = f"rounds[#{i}]"
        if not isinstance(r, dict):
            v.err(p, "expected an object")
            continue
        v.keys(r, p, keys, ("round", "opened", "closed", "openedBy", "answers"))
        if r.get("round") != i:
            v.err(_join(p, "round"), f"expected {i}")
        v.string(r, "build", p, nullable=True)
        v.integer(r, "reset", p, nullable=True)
        v.string(r, "opened", p)
        v.string(r, "openedBy", p)
        v.string(r, "results", p)
        v.string(r, "restart", p)
        last = i == len(rounds)
        if last and r.get("closed") is not None:
            v.err(_join(p, "closed"), "the last round stays open")
        elif not last and r.get("closed") is None:
            v.err(_join(p, "closed"), "only the last round is open")
        elif not last and not isinstance(r["closed"], str):
            v.err(_join(p, "closed"), "expected the time it closed")
        answers = r.get("answers")
        if isinstance(answers, dict):
            for iid, a in answers.items():
                _entry(v, a, f"{p}.answers.{iid}", False)
        elif "answers" in r:
            v.err(_join(p, "answers"), "expected an object of answers by item id")
        for k in ("checkpoints", "reopened"):
            if k in r:
                _strmap(v, r[k], _join(p, k))


def _thread(v, thread):
    if thread is None:
        return
    if not isinstance(thread, dict):
        v.err("thread", "expected an object of replies by item id")
        return
    for key, replies in thread.items():
        tp = f"thread.{key}"
        if not isinstance(replies, list):
            v.err(tp, "expected a list of replies")
            continue
        for i, r in enumerate(replies, 1):
            p = f"{tp}[#{i}]"
            if not isinstance(r, dict):
                v.err(p, "expected an object")
                continue
            v.keys(r, p, ("n", "from", "at", "round", "text", "action", "reason", "ref"), ("n", "from", "at", "text"))
            if r.get("n") != i:
                v.err(_join(p, "n"), f"expected {i}")
            for k in ("from", "at", "text", "reason", "ref"):
                v.string(r, k, p)
            v.integer(r, "round", p, minimum=1)
            v.choice(r, "action", p, ACTIONS)


def _submissions(v, subs):
    if subs is None:
        return
    if not isinstance(subs, list):
        v.err("submissions", "expected a list")
        return
    for i, s in enumerate(subs, 1):
        p = f"submissions[#{i}]"
        if not isinstance(s, dict):
            v.err(p, "expected an object")
            continue
        v.keys(s, p, ("n", "kind", "at", "to", "round", "rev", "items", "file", "state", "takenAt"), ("n", "kind", "at"))
        if s.get("n") != i:
            v.err(_join(p, "n"), f"expected {i}")
        v.choice(s, "kind", p, SUBMISSION_KINDS)
        v.string(s, "at", p, required=True)
        for k in ("to", "file", "takenAt"):
            v.string(s, k, p)
        v.integer(s, "round", p, minimum=1)
        v.integer(s, "rev", p, minimum=0)
        v.strings(s, "items", p)
        v.choice(s, "state", p, SUBMISSION_STATES)


def main(argv):
    if len(argv) != 2:
        print("usage: schema.py PAGE.json", file=sys.stderr)
        return 2
    with open(argv[1], encoding="utf-8") as f:
        errors = validate(json.load(f))
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

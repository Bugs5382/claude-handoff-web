#!/usr/bin/env python3
"""The one writer for handoff.page/v1 page files.

Every write takes an exclusive flock on <slug>.json.lock, reads the file, changes it, validates the result with
schema.py, writes a temp file and renames it into place, so the browser and an agent never clobber each other.
Rounds, revs, reply numbers and submissions all count from 1.

    from pagefile import write_definition, save_answers, new_round, restart, reply, set_route, load, item_states
"""
import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime

from schema import DEFAULT_TYPE, SCHEMA, TYPE_ANSWERS, validate

MAX_BYTES = 2 * 1024 * 1024
SERVER_KEYS = ("rev", "rounds", "thread", "submissions", "route")
DEFINITION_KEYS = ("schema", "kind", "title", "summary", "build", "reset", "status", "options", "items")


class PageError(Exception):
    def __init__(self, errors):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("; ".join(self.errors))


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def item_hash(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def item_type(doc, item):
    return item.get("type", DEFAULT_TYPE[doc["kind"]])


def allowed_answers(doc, item):
    """The answers an item takes: a tuple of values, None for free text, or () when it isn't answerable."""
    typ = item_type(doc, item)
    if typ == "question":
        return None
    if typ == "info":
        return ()
    if typ == "choice":
        return tuple(c["value"] for c in doc["options"]["choices"])
    base = tuple(item.get("answers") or TYPE_ANSWERS[typ])
    if item.get("skip") and "skipped" not in base:
        base += ("skipped",)
    return base


@contextlib.contextmanager
def _locked(path):
    path = os.fspath(path)
    with open(path + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield path
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _commit(path, doc):
    errors = validate(doc)
    if errors:
        raise PageError(errors)
    doc["rev"] = doc.get("rev", 0) + 1
    data = json.dumps(doc, indent=2, ensure_ascii=False).encode() + b"\n"
    if len(data) > MAX_BYTES:
        raise PageError(f"page file would be {len(data)} bytes; the cap is {MAX_BYTES}")
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix="." + os.path.basename(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise
    return doc["rev"]


def _round(n, build, reset, at, opened_by):
    return {"round": n, "build": build, "reset": reset, "opened": at, "closed": None, "openedBy": opened_by,
            "answers": {}, "checkpoints": {}, "reopened": {}}


def _open_next(doc, at, opened_by, results=None):
    cur = doc["rounds"][-1]
    cur["closed"] = at
    if results is not None:
        cur["results"] = results
    nxt = _round(cur["round"] + 1, doc.get("build"), doc.get("reset"), at, opened_by)
    # A reopen nobody has answered yet stays open in the next round.
    nxt["reopened"] = {k: v for k, v in cur.get("reopened", {}).items() if k not in cur["answers"]}
    doc["rounds"].append(nxt)
    return nxt


def _items_by_id(doc):
    return {it["id"]: it for it in doc["items"]}


def write_definition(path, definition, *, now=None):
    """Create the page, or replace its definition. A build or reset change opens a new round. Returns the rev."""
    refused = [f"{k}: written by the server, not the definition" for k in SERVER_KEYS if k in definition]
    if refused:
        raise PageError(refused)
    at = now or now_iso()
    with _locked(path) as p:
        if os.path.exists(p):
            doc = load(p)
            old_build, old_reset = doc.get("build"), doc.get("reset")
            for k in DEFINITION_KEYS:
                doc.pop(k, None)
            doc.update(definition)
            if doc.get("build") != old_build:
                _open_next(doc, at, "build changed")
            elif doc.get("reset") != old_reset:
                _open_next(doc, at, "reset")
        else:
            doc = dict(definition)
            doc.setdefault("schema", SCHEMA)
            doc["rev"] = 0
            doc["rounds"] = [_round(1, doc.get("build"), doc.get("reset"), at, "created")]
            doc["thread"] = {}
            doc["submissions"] = []
        return _commit(p, doc)


def set_route(path, to, mode):
    """The operator's per-page route. Returns the rev."""
    with _locked(path) as p:
        doc = load(p)
        doc["route"] = {"to": to, "mode": mode}
        return _commit(p, doc)


def save_answers(path, answers, *, by, base=None, now=None):
    """Merge one tab's changed answers ({id: {answer, note}}) into the open round, item by item.

    base is the rev the tab last saw. A stale base is fine: only the items this tab sent are laid over the file.
    Returns the rev.
    """
    at = now or now_iso()
    with _locked(path) as p:
        doc = load(p)
        items = _items_by_id(doc)
        rnd = doc["rounds"][-1]
        errors = []
        changed = False
        for iid, new in answers.items():
            item = items.get(iid)
            if item is None:
                errors.append(f"{iid}: no item {iid} on this page")
                continue
            answer, note = str(new.get("answer", "")), str(new.get("note", ""))
            ok = allowed_answers(doc, item)
            if ok == ():
                errors.append(f"{iid}: this item takes no answer")
                continue
            if ok is not None and answer and answer not in ok:
                errors.append(f"{iid}: expected one of " + ", ".join(ok))
                continue
            if answer == "changes" and not note.strip():
                errors.append(f"{iid}: Changes needs a note")
                continue
            old = rnd["answers"].get(iid)
            if old is None and not answer:
                continue
            if old is not None and old["answer"] == answer and old.get("note", "") == note:
                continue
            entry = {"answer": answer, "note": note, "by": by, "at": at, "hash": item_hash(item)}
            if old is not None:
                entry["was"] = old.get("was", []) + [{k: old[k] for k in ("answer", "note", "by", "at") if k in old}]
            rnd["answers"][iid] = entry
            rnd.get("reopened", {}).pop(iid, None)
            if answer == "yes" and item.get("checkpoint"):
                rnd.setdefault("checkpoints", {}).setdefault(item["checkpoint"], at)
            changed = True
        if errors:
            raise PageError(errors)
        return _commit(p, doc) if changed else doc["rev"]


def new_round(path, *, opened_by="saved", results=None, now=None):
    """Save round now: close the open round, keeping its Copy results text, and open the next. Returns its number."""
    with _locked(path) as p:
        doc = load(p)
        nxt = _open_next(doc, now or now_iso(), opened_by, results)
        _commit(p, doc)
        return nxt["round"]


def restart(path, checkpoint, *, by, results=None, now=None):
    """Restart a journey from a checkpoint reached in any round: the steps up to it carry over as Yes."""
    at = now or now_iso()
    with _locked(path) as p:
        doc = load(p)
        reached = {}
        for r in doc["rounds"]:
            for cp, t in r.get("checkpoints", {}).items():
                reached.setdefault(cp, t)
        upto = next((n for n, it in enumerate(doc["items"]) if it.get("checkpoint") == checkpoint), None)
        if checkpoint not in reached or upto is None:
            raise PageError(f"checkpoint {checkpoint}: not reached yet")
        keep = {it.get("checkpoint") for it in doc["items"][: upto + 1]} - {None}
        nxt = _open_next(doc, at, f"restart from {checkpoint}", results)
        nxt["restart"] = checkpoint
        nxt["reopened"] = {}
        nxt["checkpoints"] = {cp: t for cp, t in reached.items() if cp in keep}
        for it in doc["items"][: upto + 1]:
            if allowed_answers(doc, it):
                nxt["answers"][it["id"]] = {"answer": "yes", "note": "", "by": by, "at": at, "hash": item_hash(it)}
        _commit(p, doc)
        return nxt["round"]


def reply(path, item_id, frm, text, *, action=None, reason=None, ref=None, now=None):
    """Append a reply under an item (or "_page"). A reopen action reopens the item. Returns the reply number."""
    at = now or now_iso()
    with _locked(path) as p:
        doc = load(p)
        if item_id != "_page" and item_id not in _items_by_id(doc):
            raise PageError(f"{item_id}: no item {item_id} on this page")
        rnd = doc["rounds"][-1]
        replies = doc["thread"].setdefault(item_id, [])
        entry = {"n": len(replies) + 1, "from": frm, "at": at, "round": rnd["round"], "text": text}
        for k, val in (("action", action), ("reason", reason), ("ref", ref)):
            if val is not None:
                entry[k] = val
        replies.append(entry)
        if action == "reopen" and item_id != "_page":
            rnd.setdefault("reopened", {})[item_id] = reason or text
        _commit(p, doc)
        return entry["n"]


def item_states(doc):
    """Where each answerable item stands in the open round.

    {id: {"answer", "hidden", "reopened", "round"}}: a Yes from an earlier round is hidden; a reopen, or a
    definition change since the item's last Yes, makes it open again with the reason.
    """
    items = [it for it in doc["items"] if allowed_answers(doc, it) != ()]
    rounds = doc["rounds"]
    cur = rounds[-1]
    out = {}
    for it in items:
        iid, h = it["id"], item_hash(it)
        state = {"answer": "", "hidden": False, "reopened": cur.get("reopened", {}).get(iid), "round": None}
        mine = cur["answers"].get(iid)
        if mine and mine["answer"]:
            if mine["answer"] == "yes" and mine.get("hash") not in (None, h):
                state["reopened"] = f"changed since round {cur['round']}"
            elif state["reopened"] is None:
                state.update(answer=mine["answer"], round=cur["round"])
        elif state["reopened"] is None and not cur.get("restart"):
            for r in reversed(rounds[:-1]):
                a = r["answers"].get(iid)
                if a and a["answer"]:
                    if a["answer"] == "yes":
                        if a.get("hash") not in (None, h):
                            state["reopened"] = f"changed since round {r['round']}"
                        else:
                            state.update(answer="yes", hidden=True, round=r["round"])
                    break
                if r.get("restart"):
                    break
        out[iid] = state
    return out


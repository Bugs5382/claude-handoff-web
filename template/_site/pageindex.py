#!/usr/bin/env python3
"""Page files as index cards, shared by serve.py (the /_index/ API and the on-request indexes) and gen-index.py.

page_file() resolves "<folder>/<slug>" to its handoff.page/v1 file, discover_page_files() finds every page file
under a folder, and page_card() makes one card in the shape gen-index.py's collect() gives an HTML page, so the
same ordering, chips and counts apply to both.
"""
import datetime as dt
import json
import os
import re

import pagefile

PAGE_SEG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,80}$")


def page_file(root, rel):
    """Resolve "<folder>/<slug>" (or deeper) to its handoff.page/v1 file inside root, or None."""
    parts = rel.split("/")
    if len(parts) < 2 or not all(PAGE_SEG_RE.match(x) for x in parts):
        return None
    fn = os.path.join(root, *parts) + ".json"
    if os.path.realpath(fn) != os.path.join(os.path.realpath(root), *parts) + ".json" or not os.path.isfile(fn):
        return None
    try:
        with open(fn) as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    return fn if isinstance(doc, dict) and doc.get("schema") == pagefile.SCHEMA else None


def discover_page_files(root, folder):
    """(rel, path) for every page file under a folder, at any depth, skipping _ and . folders."""
    out = []
    fdir = os.path.join(root, folder)
    for dirpath, dirnames, filenames in os.walk(fdir):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(("_", ".")))
        for fn in sorted(filenames):
            if not fn.endswith(".json") or fn.startswith(("_", ".")):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn[:-5]), root).replace(os.sep, "/")
            path = page_file(root, rel)
            if path:
                out.append((rel, path))
    return out


def page_card(folder, rel, path):
    """One index card for a page file, in the same shape gen-index.py's collect() gives an HTML page."""
    doc = pagefile.load(path)
    s = pagefile.summary(doc)
    states = pagefile.item_states(doc)
    st = doc.get("status") or {}
    # Open questions never hold up approval, so they keep only a questions page in Needs you.
    questions = doc["kind"] == "questions" and any(
        pagefile.item_type(doc, it) == "question" and not states[it["id"]]["answer"] for it in doc["items"])
    if st.get("state"):
        state = st["state"]
    elif doc["kind"] in ("reference", "status"):
        state = "reference"
    else:
        # Done only once approved: a No or Changes answer keeps the page up top until the next round.
        state = "done" if s["approved"] and not questions else "needs-you"
    chips = []
    if state == "needs-you" and (s["open"] or questions or s["tally"] is not None):
        chips.append("To review")
    if s["reopened"]:
        chips.append("Reopened")
    if s["approved"]:
        chips.append("Approved")
    chips.append({"reference": "Reference", "done": "Done"}.get(state, ""))
    chips += [c for c in st.get("chips", []) if c]
    chips = [c for i, c in enumerate(chips) if c and c not in chips[:i]]
    tally = None
    if s["tally"] is not None:
        labels = {c["value"]: c["label"].lower() for c in doc["options"]["choices"]}
        tally = " · ".join(f"{n} {labels[v]}" for v, n in s["tally"].items())
    try:
        first = dt.datetime.fromisoformat(doc["rounds"][0]["opened"]).timestamp()
    except (ValueError, KeyError, IndexError):
        first = os.path.getmtime(path)
    return {"folder": folder, "key": rel[len(folder) + 1:], "href": "/" + rel, "title": doc["title"],
            "note": st.get("note", ""), "state": state, "chips": chips, "mtime": os.path.getmtime(path), "first": first,
            "open": s["open"] if state == "needs-you" and tally is None else None, "priority": st.get("priority", 50),
            "tally": tally, "kind": doc["kind"]}

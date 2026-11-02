#!/usr/bin/env python3
"""The sample pages in _site/samples/: one definition each, plus the steps that bring it to the state it shows.

load(folder) writes them as sample-<name> page files through pagefile.py, replacing earlier copies and nothing else,
so loading them again is also the reset.

    {"definition": {...}, "steps": [{"answers": {...}, "at": T}, {"send": [ids], "at": T}, {"reply": {...}, "at": T}]}
"""
import glob
import json
import os

import pagefile

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples")
PREFIX = "sample-"


def names():
    return sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(HERE, "*.json")))


def read(name):
    with open(os.path.join(HERE, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def _step(path, step, to):
    at = step["at"]
    if "answers" in step:
        pagefile.save_answers(path, step["answers"], by="Sample", now=at)
    elif "send" in step:
        sub = pagefile.add_submission(path, {"kind": "send", "to": to, "items": step["send"], "file": "sample-{n}.json"}, now=at)
        pagefile.hold(path, sub["n"])
    elif "email" in step:
        e = step["email"]
        asked = {"kind": "email", "to": to, "items": [e["id"]], "file": "sample-{n}.json", "instructions": e["instructions"],
                 "prose": e.get("prose"), "basedOn": e.get("basedOn")}
        sub = pagefile.add_submission(path, asked, now=at)
        pagefile.add_email(path, e["id"], to, e["subject"], e["body"], request=sub["n"], now=at)
    else:
        r = step["reply"]
        pagefile.reply(path, r["id"], to, r["text"], action=r.get("action"), reason=r.get("reason"), now=at)


def load(folder, *, route=None, name_prefix=PREFIX):
    """Write every sample into folder. Returns the page paths, in order."""
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(glob.escape(folder), name_prefix + "*.json*")):
        os.remove(old)
    out = []
    for name in names():
        sample = read(name)
        path = os.path.join(folder, name_prefix + name + ".json")
        pagefile.write_definition(path, sample["definition"])
        if route:
            pagefile.set_route(path, route, "send")
        for step in sample["steps"]:
            _step(path, step, route or "ops")
        out.append(path)
    return out

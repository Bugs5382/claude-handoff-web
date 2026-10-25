#!/usr/bin/env python3
"""Word diff for review pages: two texts in, a <div class="rvdiff"> block out.

The texts are split into sentences first (blank lines, list items, table rows and headings are their own
units), sentences are matched, and changed sentences get a word-level diff: removed words in <del>, added
words in <ins>, unchanged sentences as <p class="same">. site.css styles the block (colour plus underline
and strikethrough). Everything is HTML escaped.

Usage: diff.py OLD.txt NEW.txt    (prints the markup)
       from diff import diff_html, diff_units
"""
import difflib
import html
import re
import sys

_SENT = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[*`]?[A-Z0-9])")
_TOK = re.compile(r"\s+|\w+(?:['’\-./:]\w+)*|[^\w\s]")
_LINE_BLOCK = re.compile(r"\s*([-*#>|]|\d+\.)\s")


def units(text):
    """Sentences, after splitting on blank lines; a block of list items, table rows or headings splits by line."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if any(_LINE_BLOCK.match(ln) or ln.lstrip().startswith("|") for ln in lines):
            parts = []
            for ln in lines:
                if not ln.strip():
                    continue
                # an indented line under a list item continues it
                if parts and ln[:1] in " \t" and not _LINE_BLOCK.match(ln) and not ln.lstrip().startswith("|"):
                    parts[-1] += " " + ln.strip()
                else:
                    parts.append(ln.strip())
        else:
            parts = _SENT.split(" ".join(ln.strip() for ln in lines))
        out.extend(p for p in parts if p)
    return out


def words(old, new):
    """Inline word diff of two strings: escaped text with <del> and <ins> runs."""
    a, b = _TOK.findall(old), _TOK.findall(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(html.escape("".join(a[i1:i2])))
            continue
        if op in ("delete", "replace"):
            out.append("<del>" + html.escape("".join(a[i1:i2])) + "</del>")
        if op in ("insert", "replace"):
            out.append("<ins>" + html.escape("".join(b[j1:j2])) + "</ins>")
    return "".join(out)


def diff_units(a, b, same=True):
    """The rvdiff block from two lists of units (sentences, lines or labels). same=False leaves out unchanged units."""
    paras = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            if same:
                paras += [f'<p class="same">{html.escape(s)}</p>' for s in a[i1:i2]]
        elif op == "delete":
            paras += [f"<p><del>{html.escape(s)}</del></p>" for s in a[i1:i2]]
        elif op == "insert":
            paras += [f"<p><ins>{html.escape(s)}</ins></p>" for s in b[j1:j2]]
        elif len(a[i1:i2]) == len(b[j1:j2]):
            paras += [f"<p>{words(a[i1 + k], b[j1 + k])}</p>" for k in range(i2 - i1)]
        else:
            # A sentence split or merged: diff the run as one paragraph.
            paras.append(f"<p>{words(' '.join(a[i1:i2]), ' '.join(b[j1:j2]))}</p>")
    return '<div class="rvdiff">' + "\n".join(paras) + "</div>"


def diff_html(old, new, same=True):
    """The rvdiff block for two texts, grouped by sentence."""
    return diff_units(units(old), units(new), same)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    with open(sys.argv[1]) as fa, open(sys.argv[2]) as fb:
        print(diff_html(fa.read(), fb.read()))

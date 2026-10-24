"""site.css keeps every colour in tokens, and both dark blocks redefine all of them the same way."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "template" / "_site" / "site.css").read_text()


def block(start):
    i = CSS.find(start)
    assert i >= 0, start
    j = CSS.index("{", i)
    depth = 0
    for k in range(j, len(CSS)):
        if CSS[k] == "{":
            depth += 1
        elif CSS[k] == "}":
            depth -= 1
            if depth == 0:
                return CSS[j:k]
    raise AssertionError(f"unclosed block {start}")


def tokens(b):
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"(--[a-z0-9-]+):\s*([^;]+);", b)}


LIGHT, MEDIA, DARK = block(":root {"), block("@media (prefers-color-scheme: dark)"), block(':root[data-theme="dark"]')


def test_dark_blocks_redefine_every_colour_token():
    light, media, dark = tokens(LIGHT), tokens(MEDIA), tokens(DARK)
    colour = [k for k, v in light.items() if re.search(r"#|rgb", v)]
    assert len(colour) > 40, f"colour tokens {len(colour)}"
    assert [k for k in colour if k not in media] == [], "missing under prefers-color-scheme"
    assert [k for k in colour if k not in dark] == [], "missing under data-theme=dark"
    assert [k for k in media if media[k] != dark.get(k)] == [], "the two dark blocks differ"


def test_dark_blocks_respect_an_explicit_light_choice():
    assert ':root:not([data-theme="light"])' in MEDIA
    assert re.search(r"color-scheme:\s*dark", DARK)


def test_no_hard_coded_colours_outside_the_tokens():
    rest = CSS.replace(LIGHT, "").replace(MEDIA, "").replace(DARK, "")
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rest) == []

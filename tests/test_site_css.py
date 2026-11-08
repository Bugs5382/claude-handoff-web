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


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_diff_colours_have_contrast_in_light_and_dark():
    for b in (tokens(LIGHT), tokens(MEDIA), tokens(DARK)):
        for kind in ("ins", "del"):
            fg, bg = b[f"--diff-{kind}"], b[f"--diff-{kind}-bg"]
            assert contrast(fg, bg) >= 4.5, (kind, fg, bg, contrast(fg, bg))


def rule(selector):
    m = re.search(re.escape(selector) + r"[^{]*\{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


def test_diff_marks_do_not_rely_on_colour_alone():
    ins, dele = rule(".site .rvdiff ins"), rule(".site .rvdiff del")
    assert "underline" in ins and "var(--diff-ins)" in ins and "var(--diff-ins-bg)" in ins
    assert "line-through" in dele and "var(--diff-del)" in dele and "var(--diff-del-bg)" in dele
    assert "var(--muted)" in rule(".site .rvdiff .same")


def test_diff_keeps_line_breaks_and_code_is_monospace():
    assert "white-space: pre-wrap" in rule(".site .rvdiff p")
    code = rule(".site .rvdiff.code")
    assert "monospace" in code and "overflow-x: auto" in code


def test_final_view_hides_removed_text_and_plains_the_rest():
    assert "display: none" in rule(".site .rvdiff.final del")
    ins = rule(".site .rvdiff.final ins")
    assert "text-decoration: none" in ins and "background: none" in ins and "color: inherit" in ins
    assert "color: inherit" in rule(".site .rvdiff.final .same")


# WCAG 2.2 AA, measured per theme: 4.5:1 for text, 3:1 for non-text parts of controls.
TEXT_PAIRS = [
    ("--ink", "--paper"), ("--ink", "--card"), ("--ink-2", "--card"), ("--ink-2", "--soft"),
    ("--muted", "--paper"), ("--muted", "--card"), ("--muted", "--soft"), ("--muted", "--soft-2"),
    ("--link", "--paper"), ("--link", "--card"), ("--link", "--soft"), ("--link", "--accent-soft"),
    ("--link-hover", "--card"), ("--accent-dark", "--accent-soft"), ("--accent-dark", "--card"),
    ("--yes", "--yes-bg"), ("--yes", "--card"), ("--chg", "--chg-bg"), ("--chg", "--card"),
    ("--no", "--no-bg"), ("--no", "--card"), ("--info", "--info-bg"), ("--info", "--card"),
    ("--upd", "--upd-bg"), ("--upd", "--card"), ("--blk", "--blk-bg"),
    ("--on-solid", "--yes-solid"), ("--on-solid", "--chg-solid"), ("--on-solid", "--no-solid"),
    ("--on-solid", "--skip-solid"), ("--on-solid", "--other-solid"),
    ("--on-bar", "--bar"), ("--on-bar", "--bar-done"), ("--bar-btn-done-ink", "--bar-btn-done-bg"),
    ("--toast-ink", "--toast-bg"), ("--pic-ink", "--pic-bg"),
]
NON_TEXT_PAIRS = [
    ("--focus", "--paper"), ("--focus", "--card"), ("--icon", "--card"), ("--accent", "--card"),
    ("--ring-blocker", "--card"),
]


def theme_tokens():
    light = tokens(LIGHT)
    return {"light": light, "dark (system)": {**light, **tokens(MEDIA)}, "dark (toggle)": {**light, **tokens(DARK)}}


def test_text_pairs_meet_aa_in_light_and_dark():
    bad = []
    for theme, t in theme_tokens().items():
        for fg, bg in TEXT_PAIRS:
            r = contrast(t[fg], t[bg])
            if r < 4.5:
                bad.append((theme, fg, bg, t[fg], t[bg], round(r, 2)))
    assert bad == []


def test_non_text_parts_meet_3_to_1_in_light_and_dark():
    bad = []
    for theme, t in theme_tokens().items():
        for fg, bg in NON_TEXT_PAIRS:
            r = contrast(t[fg], t[bg])
            if r < 3:
                bad.append((theme, fg, bg, t[fg], t[bg], round(r, 2)))
    assert bad == []


def test_no_blue_is_left_in_the_palette():
    for theme, t in theme_tokens().items():
        for name in ("--link", "--accent", "--focus", "--icon", "--info"):
            h = t[name].lstrip("#")
            r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
            assert not (b > r + 20 and b > g), (theme, name, t[name])


def test_warren_mark_files_match_the_repo_asset_and_follow_the_theme_tokens():
    site = ROOT / "template" / "_site"
    asset = ROOT.parent.parent / "assets" / "warren-mark.svg"
    if asset.exists():  # absent when the adapter is checked out on its own
        assert (site / "warren-mark.svg").read_text() == asset.read_text()
    light, dark = tokens(LIGHT), tokens(DARK)
    assert "warren-mark-light.svg" in light["--mark"] and "warren-mark-dark.svg" in dark["--mark"]
    for name, cols in (("light", ("#4f7a3a", "#8a6a4a", "#d98c2b", "#e0a93a", "#c4622d")),
                       ("dark", ("#7fb069", "#c9a27a", "#f0a640", "#f5c25a", "#e07a45"))):
        text = (site / f"warren-mark-{name}.svg").read_text().lower()
        assert all(c in text for c in cols), name


def test_every_page_shell_links_the_favicon_and_the_header_mark_is_css():
    for f in ("app.html", "build-review.py"):
        assert 'rel="icon"' in (ROOT / "template" / "_site" / f).read_text(), f
    assert "rel=icon" in (ROOT / "template" / "gen-index.py").read_text()
    assert "header.top h1::before" in CSS and "var(--mark)" in CSS

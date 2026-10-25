"""Tests for template/_site/diff.py: two texts in, a word diff grouped by sentence out, as rvdiff markup."""

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIFF = ROOT / "template" / "_site" / "diff.py"


def load():
    spec = importlib.util.spec_from_file_location("site_diff", DIFF)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def paras(markup):
    assert markup.startswith('<div class="rvdiff">') and markup.endswith("</div>"), markup
    return markup[len('<div class="rvdiff">'):-len("</div>")].split("\n")


def test_identical_texts_are_all_unchanged_context():
    out = load().diff_html("One. Two.", "One. Two.")
    assert "<ins>" not in out and "<del>" not in out
    assert paras(out) == ['<p class="same">One.</p>', '<p class="same">Two.</p>']


def test_a_changed_word_is_marked_inside_its_own_sentence():
    out = load().diff_html("The core ran slowly. It never closed.", "The core ran fast. It never closed.")
    assert paras(out) == ["<p>The core ran <del>slowly</del><ins>fast</ins>.</p>", '<p class="same">It never closed.</p>']


def test_added_and_removed_sentences_are_whole_runs():
    out = load().diff_html("Keep this. Drop this.", "Keep this. Add this.")
    assert '<p class="same">Keep this.</p>' in paras(out)
    assert "<del>Drop</del><ins>Add</ins>" in out
    out = load().diff_html("Keep this.", "Keep this. A new one.")
    assert paras(out) == ['<p class="same">Keep this.</p>', "<p><ins>A new one.</ins></p>"]
    out = load().diff_html("Keep this. Gone now.", "Keep this.")
    assert paras(out) == ['<p class="same">Keep this.</p>', "<p><del>Gone now.</del></p>"]


def test_text_is_html_escaped():
    out = load().diff_html("Use <b> tags & such.", "Use <i> tags & such.")
    assert "<b>" not in out and "&lt;" in out and "&amp;" in out


def test_list_items_and_table_rows_are_their_own_units():
    old = "- first item\n- second item\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    new = "- first item\n- second thing\n\n| a | b |\n|---|---|\n| 1 | 3 |"
    ps = paras(load().diff_html(old, new))
    assert '<p class="same">- first item</p>' in ps
    assert any("<del>item</del><ins>thing</ins>" in p for p in ps)
    assert any("<del>2</del><ins>3</ins>" in p for p in ps)


def test_same_false_leaves_out_unchanged_units():
    out = load().diff_units(["a", "b", "c"], ["a", "B", "c"], same=False)
    assert paras(out) == ["<p><del>b</del><ins>B</ins></p>"]


def test_command_line_prints_the_markup(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("Old words here.")
    b.write_text("New words here.")
    r = subprocess.run([sys.executable, str(DIFF), str(a), str(b)], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == '<div class="rvdiff"><p><del>Old</del><ins>New</ins> words here.</p></div>'

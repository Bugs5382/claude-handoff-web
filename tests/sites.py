"""Folders for the test sites. The HTML tests use today's HTML demo pages, kept in tests/data/html-example since
example/ holds page files; folders not kept there (guide) come from example/."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML_EXAMPLE = ROOT / "tests" / "data" / "html-example"


def html_example(folder):
    return HTML_EXAMPLE / folder if (HTML_EXAMPLE / folder).is_dir() else ROOT / "example" / folder

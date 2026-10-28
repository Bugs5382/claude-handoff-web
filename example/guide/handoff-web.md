---
name: handoff-web
description: How to publish pages for the owner on the claude-handoff-web review site (page files, page.py, the inbox, review rules)
type: reference
---
- The site is a working folder served by `_site/serve.py` at `http://<host>:<port>/` (see its `site.json`); it is scratch memory, never a git repo, never committed.
- One server, one port, run by the operator session. Never start another server; never open a browser for the owner. Give links as plain text.
- Publish only into your own folder. A page is one JSON file, `<folder>/<slug>.json` (`handoff.page/v1`), created with `python3 _site/page.py new <folder>/<slug> --from def.json` and changed with `page.py set`. Never edit it by hand. Its link is `http://<host>:<port>/<folder>/<slug>`.
- A page file needs no `_status.json` entry and no index rebuild: its card comes from the file (`page.py status <page> needs-you|reference|done --note "..."`).
- Kinds: `review` (Yes / No / Changes), `checklist` (adds Skipped, needs a `build`), `journey` (ordered steps, checkpoints, Restart from), `backlog` (the page's own `options`, such as Start / Hold), `questions` (free text), `reference` and `status` (no answers). Any item can set its own `type`, so one page can mix sections, questions, choices, steps and info items.
- Changes needs a note. Free-text questions never block approval. Choices count as their default until picked.
- Answers are saved in the page file as the owner goes. Send and "Blocker: send now" land in `_inbox/<agent>/`; keep `python3 _site/page.py wait <agent>` running in the background, take each file (move it to `taken/`), act, then answer on the page with `page.py reply <page> <id> --from <agent> "..."`.
- Reopen an item with `page.py reply ... --reopen "reason"`; clear a `blockedBy` with `--action unblock`. An earlier Yes stays hidden unless the item's content changes.
- A new `build` or `reset` opens a new round; rounds stay in the file and show under History and `/<folder>/history/`.
- Pictures are files next to the page (`img/x.png`), never embedded. A rewrite to review is a `diff` item or block (`old`, `new`).
- Never ask twice: if a checklist answered it, close the review item from that answer.
- The owner's Stale button marks a page done and moves the file to `_old/`, pruned after 7 days.
- Check a file with `page.py check <page>`; every error names its JSON path.
- HTML pages not converted yet keep the old rules (`_status.json`, `gen-index.py`, `/_save/`); convert one with `page.py convert <folder>/<page>.html`.
- Scratch files go in your own temp folder, not the site.
- Page kinds with examples: `docs/page-types.md` in the template repo; the format: `_site/PAGE-FILE.md`; the API and inbox: `_site/PAGE-API.md`.

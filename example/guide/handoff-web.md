---
name: handoff-web
description: How to publish pages for the owner on the claude-handoff-web review site (one server, own folder, _status.json, review rules)
type: reference
---
- The site is a working folder served by `_site/serve.py` at `http://<host>:<port>/` (see its `site.json`); it is scratch memory, never a git repo, never committed.
- One server, one port, run by the operator session. Never start another server; never open a browser for the owner. Give links as plain text.
- Publish only into your own folder (`/<folder>/`). Every page gets a `_status.json` entry (`needs-you`, `reference` or `done` plus a one-line note); then run `python3 gen-index.py`.
- Load `/_site/site.css?v=12` and `/_site/review.js?v=12`; use `<body class="site">`.
- Review pages: each `<h2>` or `[data-review-question]` item gets Yes / No / Changes (Changes needs a note); checklists add Skipped with `data-review-skip="on"`.
- Answers are saved on the server (`/_save/`), never only in the browser; the owner pastes "Copy results" back to you.
- Set `data-review-approved` from the pasted results (hidden, kept in Copy results); bring items back with `data-review-reopen="id=reason"`.
- Blockers ("Blocker: copy now") go to the front of the queue. Dependent items use `data-review-blocked="id=blocker"`.
- Something that isn't a choice (a free-text answer) is an open question, not a Yes/No/Changes item:
  `data-review-type="question"` (optional `data-suggested="..."`). It never blocks approval and is never
  counted in the open-items count; Copy results lists it as `Q <id>: <answer>`.
- Keep one unified page per session: `python3 _site/build-review.py <folder>` builds `/<folder>/review/`.
- Never ask twice: if a checklist answered it, close the review item from that answer.
- The owner's Stale button deletes a page for good; `_old/` copies are pruned after 7 days. A page's round
  history is never deleted by Stale or the `_old/` prune.
- A round is one pass of answers under one `data-build` or `data-review-reset` version; bumping either one
  archives the round it replaces automatically (`_saved/history/`). Nothing to do beyond keeping those
  attributes current. Past rounds: a collapsed "History" block per page, the More menu, `/<folder>/history/`.
- Scratch files go in your own temp folder, not the site.
- Page designs and skeletons: `docs/page-types.md` in the template repo; operating notes: `_site/README.md`.

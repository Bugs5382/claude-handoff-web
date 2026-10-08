# Operating rules for this hand-off site

This folder is a running instance of claude-handoff-web: a review and sign-off site where agents publish
pages and the owner (`site.json` `owner`) answers them. Every agent or session that touches it follows
these rules. Full how-to: `_site/README.md`; page designs: the template's `docs/page-types.md`.

## Working memory, never a repo

- This folder is scratch memory. Never `git init` it, never commit it, never copy its pages, `_status.json`
  or `_saved/` into a repository. `serve.py` refuses to start inside a git work tree.
- Scratch and temp files go in a temp dir (a per-session or per-lane scratch folder), not here, unless the
  owner wants them kept.

## One server, one folder each

- One server, one port, run by the operator session (`_site/serve.py`, host and port from `site.json`).
  Never start another web server.
- Each session publishes only into its own folder (listed in `site.json` `folders`). The operator owns the
  root, `site.json` and `_site/`.
- Every page you add gets an entry in your folder's `_status.json` (`needs-you`, `reference` or `done`,
  with a one-line note), then run `python3 gen-index.py`.
- Give links as plain text (`http://<host>:<port>/<folder>/<page>.html`). Never open a browser for the
  owner unless asked.

## Stale and _old/

- The owner's Stale button deletes a page for good and marks it done; don't recreate it unless asked.
- Before you replace a file, copy it to its folder's `_old/`. Files in `_old/` are pruned after 7 days.

## Reviews

- Every item gets Yes / No / Changes (notes required for Changes); test checklists add Skipped (locked).
- Approved items are hidden (set them from the owner's pasted results with `data-review-approved`) and stay
  in Copy results. An answered item comes back only when a change alters it, marked Reopened with the reason
  (`data-review-reopen`).
- Every item has "Blocker: copy now"; a pasted blocker goes to the front of the queue.
- Items that need another item to pass first are `data-review-blocked`: greyed and not counted until the
  blocker is fixed.
- Never ask twice: when a checklist already answered something a review asks, close the review item from
  that answer.
- Each session keeps one unified page at `/<folder>/review/` (`python3 _site/build-review.py <folder>`)
  holding every open item from its review pages. Nothing is built or merged until every item is Yes.
- Answers are saved on the server through `/_save/` (see `_site/SAVE-API.md`); a page never keeps answers
  only in the browser.

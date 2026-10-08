# The hand-off site

Served by `_site/serve.py` from this folder, at the host and port in `site.json`. The operator owns the root,
`site.json` and `_site/`; each session publishes only into its own folder. Run one server only.

## Mark a page

1. Edit your folder's `_status.json`. The key is the page path inside the folder (`x.html`, `dir/`, `dir/y.html`):

   ```json
   "review/": { "state": "needs-you", "note": "One line on why.", "chips": ["Decision needed"] }
   ```

   `state` is `needs-you`, `reference` or `done`. `chips` is optional; `priority` (default 50, lower first)
   sorts the root list. `first_seen` is added by the script; leave it.
2. Run `python3 gen-index.py`.

A page that isn't in the manifest shows under "Needs you" with a "Not classified" chip. When a page's item
completes, set it to `done` and it moves to "Completed". To retire a page, the owner presses Stale.

## Hook a page in

```html
<link rel="stylesheet" href="/_site/site.css?v=10">
...
<script src="/_site/review.js?v=10"></script>   <!-- review pages: just before </body> -->
```

- `review.js` turns every `<h2>` section (and every `[data-review-question="id" data-title="..."]`) into an
  item with Yes / No / Changes. It loads `live.js` itself.
- Body attributes: `data-review-approved="s1,s3"` (Yes from pasted results: hidden, kept in Copy results),
  `data-review-reopen="s4=reason|s5=reason"`, `data-review-reset="v2:s4,s5"` (bump the version once after a
  rework; cleared answers are archived in the saved state, not lost), `data-review-blocked="s6=s2"` (greyed
  until its blocker is fixed), `data-build="1.2.3"` (shown in How to test and blocker copies).
- Answers live on the server only, in `_saved/<page-key>.json` through `/_save/` (see `SAVE-API.md`). The
  page key is `KEY_PREFIX` (top of `review.js`, from `site.json` `key_prefix`) plus the page path,
  sanitised. Answers an older copy kept in the browser's localStorage under that key are uploaded once,
  read back, then removed from the browser. Saves are debounced 500 ms and retried; the bar shows
  "Saved hh:mm" or "Not saved, retrying".
- Unified page: `python3 _site/build-review.py <folder>` builds `/<folder>/review/` from every needs-you page
  in its `_status.json`; rerun it after a source page or the manifest changes. Each source page is one
  collapsed group (one open at a time) whose heading shows the title, a one-line summary
  (`<meta name="description">`, else the first paragraph, else the manifest note), the open count, chips,
  "Full page" and Stale. Each item shows its question and answer controls first; bulky content sits behind
  "Show details". A folder with its own builder lists it in `site.json` `builders`.
- Converted pages wrap each item in `<section data-review-question="id" data-title="...">` and set
  `<body data-review-h2="off">` so only those sections are items. `data-review-skip="on"` adds Skipped (locked)
  for test checklists; `data-review-import="oldKey|prefix"` imports answers an older checklist saved.
- `data-review-stale="a.html|b/"` (set by build-review.py from `_saved/stale-log.json`, last 7 days) lists
  those pages as `STALE: <page>` in Copy results.
- Pages without review.js (checklists, indexes) load `/_site/live.js` (`data-mode="page"` on non-index pages).
- Element styles apply only under `<body class="site">`; design mocks can load site.css without losing their look.

## Bottom bar (lean, for now)

One line: the count and the Saved status, Previous / Next, "Open ids (n)" (the open-id chips fold behind it)
and More (Copy results, Clear my answers). The n and p keys jump between open items. A fuller redesign of
the bar is planned; keep changes here small until then.

## Live

Indexes and review pages poll themselves every 10 s (paused while the tab is hidden). Indexes swap their cards
in place and light up "New"/"Updated". Review pages reload softly, never while the owner is typing, within 5 s
of a click, or while answers are unsaved, and keep the scroll position. Just write the file and rerun
gen-index.py; nobody needs to refresh.

## How to test (pop-out)

Test steps never sit inline with the answers. Put them in a `<template data-howto>` inside the item (or its
h2 section); review.js adds a "How to test" button next to the item title that opens the steps in one named
pop-out window (`howto`, 520x720, reused), styled with site.css, showing the item id, title and `data-build`.
Every `<pre>` and `code.cmd` in it gets a Copy button. Existing `class="howto"` blocks and checklist
`.item .how` lines are converted automatically. Checklists with their own answer script and pop-out load
review.js with `<body data-review-controls="off">`: review.js then only starts live updates.

## Wording

- Answers, review pages: Yes, No, Changes (notes required for Changes). Test checklists add Skipped.
- Item states: Open, Reopened: <reason>, Approved, Skipped (locked), Blocked by <id>.
- Buttons: Copy results, Clear my answers (never clears approved or locked items), Blocker: copy now,
  Stale: remove this page.
- Progress: `<n> of <m> open items answered`, plus ` · <k> approved and hidden` when k > 0.
- Copy results lines: `- [id] ANSWER: title` and `    Note: ...`; `STALE: <page>`; footer
  `APPROVED: every item is Yes.` or `Not approved yet: <n> of <m> are Yes.`
- Index sections: Needs you, Reference, Completed (collapsed). Root: Needs you now.
- Chips: New (first seen in the last 24 h), Updated, To review, Reopened, Approved, Reference, Done,
  Not classified, plus custom chips from `"chips"`.

## Operating the site

- **Config:** `site.json` at the root holds the title, owner, host, port, timezone, review windows, the
  folders (id, name, blurb), `key_prefix`, `blocker_to`, protected pages, per-folder builders and the prune
  settings. Every name on the site comes from it.
- **Server:** `nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &` (host and port from
  `site.json`; flags override). Writable endpoints: `PUT /_save/<name>.json` and `POST /_stale`; nothing
  else. `_saved/` is never served directly.
- **Stale deletes for real:** after the owner's confirm, `POST /_stale {folder, page}` checks the page is
  listed in that folder's `_status.json` and lies inside that folder (never `_site/`, `_old/`, a folder
  root, `review/` or a `protected` page), deletes it, marks it `done` with `Stale (<owner>, <date> <tz>)`,
  logs it in `_saved/stale-log.json`, and reruns the builders.
- **`_old/` pruning:** files under any `_old/` folder older than `prune_old_days` (default 7) are deleted
  hourly and listed in `_saved/prune-log.json`. Set `"prune_old": false` to keep them.
- **Never a git repo:** this folder is working memory and is never committed. `serve.py` refuses to start
  inside a git work tree, and `install.sh` refuses to install into one.
- **Root filter:** one "Projects" dropdown (checkboxes with needs-you counts, All, None). The choice stays in
  the browser (`localStorage` `site-filter`).
- **Focus and order:** optional `_site/focus.json` `{"order": [...], "focus": [...]}` overrides `site.json`
  `order`. Within a project, cards sort by `priority`, then `review/`, then the newest.

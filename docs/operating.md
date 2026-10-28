# Operating the site

## Working memory, never committed

Install by copying the template into a working folder; the working folder is scratch memory and is never
committed. When a Claude agent (or any agent) runs an instance, it never creates a git repository for it:
pages change too often. Three guards back this up:

- `install.sh` refuses a target inside a git work tree and never runs `git init`;
- `serve.py` refuses to start when the served folder is inside a git work tree;
- every instance carries `CLAUDE.md` and `AGENTS.md` saying so.

This repository holds only the generic template and the fake `example/`. Never copy a live page,
`_status.json`, `_saved/` or `_inbox/` into it; `.gitignore` keeps `_saved/`, `_old/`, `_inbox/` and every
`_status.json` outside `example/` out.

## Configuration

`site.json` at the root of the instance holds every name the site shows:

| Key | Meaning |
|---|---|
| `title`, `subtitle`, `owner` | the root heading, its line, and the person who answers (`Pages for <owner>`) |
| `host`, `port` | where `serve.py` binds (flags override) |
| `timezone`, `tz_label` | times on cards and Stale notes |
| `review_windows` | when the owner looks, for agents planning their batches |
| `folders` | `id`, `name`, `blurb` per project or session; `order` sorts them |
| `key_prefix`, `blocker_to` | the answer storage key prefix and who blockers are pasted to (stamped into `review.js` by `install.sh`) |
| `protected` | `folder/page` keys Stale must refuse (live checklists) |
| `builders` | a folder that builds its own unified page: `{"folder": "../its-builder.py"}` |
| `prune_old`, `prune_old_days` | the `_old/` clean-up |
| `operator` | the agent a page file sends to when nothing else is set (default `ops`) |
| `routes` | a folder's default route for page files: `{"folder": {"to": "app", "mode": "send"}}`, mode `send`, `copy` or `both` |

## Endpoints

| Method | Path | What |
|---|---|---|
| `GET` | any static path | files, like `python3 -m http.server`; `_saved/` and `_inbox/` are never served |
| `GET`, `PUT` | `/_save/<name>.json` | answers on HTML pages (see `_site/SAVE-API.md`) |
| `POST` | `/_stale` | `{folder, page}`: Stale |
| `GET` | `/_history/<name>/`, `/_history/<name>/<file>` | round history, read-only (see `_site/SAVE-API.md`) |
| `POST` | `/_round-close` | `{name, results_text?}`: close a round by hand |
| `GET` | `/<folder>/<slug>` | a page file, drawn by `_site/render.js` in the `_site/page.html` shell; a converted page's old `.html` URL redirects here |
| `GET` | `/_page/<folder>/<slug>` | the page file with its item states, counts, route, whether the route's agent is listening, and server-drawn diffs; send `If-None-Match` with the last `ETag` for a cheap 304 |
| `PUT` | `/_page/<folder>/<slug>/answers` | `{base, answers: {id: {answer, note}}}`: merge one tab's answers; returns `{rev}` |
| `POST` | `/_page/<folder>/<slug>/round` | `{results?}`: Save round now; returns `{round}` |
| `POST` | `/_page/<folder>/<slug>/restart` | `{checkpoint, results?}`: restart a journey and send a `restart` submission |
| `POST` | `/_page/<folder>/<slug>/send` | `{kind: send or blocker, items?, results?}`: send to the page's route; `409` when the route only copies |
| `GET` | `/_index/`, `/_index/<folder>` | index cards from the page files, merged with the HTML pages in `_status.json` |
| `GET` | `/`, `/<folder>/`, `/<folder>/history/` | built on request (with `gen-index.py`'s own HTML) when the folder, or for `/` any folder, has page files; otherwise the static `index.html` |

Nothing else is writable. A rejected page write answers `400` with `{"errors": [...]}`, each error naming the
item. `Cache-Control: no-store` is sent on `/_save/`, `/_history/`, `/_page/`, `/_index/`, `.html` files,
page URLs and folder URLs.

## Page files and the inbox

A page file is `<folder>/<slug>.json` (see `_site/PAGE-FILE.md`). Its route is the page's own `route`, else
the folder's entry in `routes`, else `operator`. Send, Blocker and Restart each write one file, atomically:

```text
_inbox/<agent>/<prio>-<UTC stamp>-<folder>-<slug>-<n>.json      prio: 0 = blocker or restart, 5 = send
```

The file is `handoff.submission/v1`: the page, its URL, title, build, round and rev, the items with their
answers and notes, and the Copy results text. File names sort blockers first. An agent takes a file by moving
it to `_inbox/<agent>/taken/`; the next read of the page records it as picked up. While an agent waits, it
keeps its pid in `_inbox/<agent>/.listening`, and the page shows it as listening only while that process is
alive. `page.py wait <agent>` does the waiting and `page.py hook <agent>` is the safety net (see
`_site/PAGE-FILE.md`).

A page file's card is in Needs you until every counted item is Yes, then Done; `status.state` overrides that,
and `reference` and `status` pages are Reference. Open questions never hold a page up, except on a
`questions` page.

## Stale

The owner's "Stale: remove this page" button (on needs-you cards and on unified review groups) deletes the
page for good after a confirm. The server only accepts a page that is listed in that folder's
`_status.json` and lies inside that folder: never `_site/`, `_old/`, a folder root, `review/` or a
`protected` page. It then marks the entry `done` with `Stale (<owner>, <date> <tz>)`, appends a line to
`_saved/stale-log.json`, and reruns the folder's builder and `gen-index.py`. Copy results on the unified page
lists recent ones as `STALE: <page>`. A page's round history is never deleted by Stale; `/_history/` reports
`page_removed: true` for it afterwards.

Stale on a page file (`{folder, page}` with `page` as the slug, such as `design` or `journeys/first-order`)
keeps everything: it marks the file `done` with the same note and moves it to `<folder>/_old/`, where the
pruner removes it after `prune_old_days`. The log line says where it went.

## _old/ pruning

Before replacing a file, copy it to its folder's `_old/`. The server deletes files under any `_old/` folder
older than `prune_old_days` (default 7) once an hour and lists them in `_saved/prune-log.json`. Set
`"prune_old": false` to keep everything. `_saved/` itself (round history included) is never walked by the
pruner.

## Round history

A round is one pass of answers under one `data-build` value or one `data-review-reset` version. Every
`PUT /_save/<name>.json` compares the page's current `data-build` and `data-review-reset` with what the
server last saw for it; when either changed, the answers from before this `PUT` are archived to
`_saved/history/<name>/<stamp>__<label>.json` first (see `_site/SAVE-API.md` for the entry's shape and the
`GET /_history/` endpoints). The round number is a sequential integer per page, computed in order, never
the build or version string. More, "Save round now" calls `POST /_round-close` to close a round by hand.
Every page shows its own rounds in one collapsed `<details>` at the bottom; `gen-index.py` builds the same,
grouped by page, at `/<folder>/history/`, linked from the root index as a small "History" per folder.
Its `history/` entry in the folder's `_status.json` is set to `reference` whenever it has no state, so the
history page never shows under Needs you; a state you set yourself is kept. The history page is written
before the folder's pages are collected, so the folder index lists it from the first `gen-index.py` run.

## Restarting

Stop the old process and start the new one straight after, so the gap is a fraction of a second:

```bash
kill <old-pid>; nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

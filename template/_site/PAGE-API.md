# Page API: page files over HTTP, and the inbox

How the browser reads and answers a page file, and how a Send or a Blocker reaches an agent. `render.js` and
`review.js` already use all of this; agents write page files with `page.py` (see `PAGE-FILE.md`) and read
their inbox from disk. HTML pages that aren't converted yet keep using `/_save/` (`SAVE-API.md`).

## Before you start

- A running site, and a page file to try it on. From the site folder:

  ```bash
  printf '%s' '{"schema": "handoff.page/v1", "kind": "review", "title": "Try it", "items": [{"id": "s1", "title": "First"}, {"id": "s2", "title": "Second"}]}' > try.json
  python3 _site/page.py new demo/try --from try.json
  ```

- The examples use `http://127.0.0.1:8000`; use the host and port from `site.json`.

## Endpoints

`<page>` is `<folder>/<slug>`, or deeper (`demo/journeys/first-order`).

| Method | Path | Body | Result |
|---|---|---|---|
| `GET` | `/<page>` | none | the page, drawn by `render.js` in `_site/page.html`; a converted page's old `.html` URL answers `301` to it |
| `GET` | `/_page/<page>` | none | `200` with the page as JSON (below) and an `ETag`; `304` when `If-None-Match` matches |
| `PUT` | `/_page/<page>/answers` | `{"base": rev, "answers": {id: {"answer": "...", "note": "..."}}}` | `200` with `{"rev": n}` |
| `POST` | `/_page/<page>/round` | `{"results": "..."}` | `200` with `{"round": n}`: Save round now; `n` is the round just opened |
| `POST` | `/_page/<page>/restart` | `{"checkpoint": "...", "results": "..."}` | `200` with `{"round": n, ...}` and a `restart` submission |
| `POST` | `/_page/<page>/send` | `{"kind": "send" or "blocker", "items": [ids], "results": "..."}` | `200` with `{"n", "file", "to", "listening"}` |
| `GET` | `/_index/` and `/_index/<folder>` | none | the index cards as JSON, with an `ETag` |

- Request bodies are JSON with `Content-Type: application/json`, at most 256 KB. Wrong type: `415`. Not
  JSON: `400`. Too large: `413`. No such page: `404`. Unknown action: `405`.
- A write the page file refuses answers `400` with `{"errors": ["s1: Changes needs a note"]}`, each error
  naming the item.
- Every response carries `Cache-Control: no-store`. `_saved/` and `_inbox/` are never served.

### Reading a page

```bash
curl -s http://127.0.0.1:8000/_page/demo/try | python3 -m json.tool | head -20
```

The body is `{"page", "states", "summary", "route", "listening", "diffs"}`:

- `page`: the page file as stored, including `rev`, `rounds`, `thread` and `submissions`.
- `states`: per answerable item, `{"answer", "hidden", "reopened", "round"}`. `hidden` is a Yes from an earlier
  round; `reopened` is the reason it came back, or `null`.
- `summary`: the bar's counts, `open`, `blocked`, `counted`, `yes`, `reopened`, `approved`, and a backlog's
  `tally`.
- `route`: where Send goes, `{"to": agent, "mode": "send" | "copy" | "both"}`. It's the page's own `route`, else
  the folder's in `site.json` `routes`, else `operator`.
- `listening`: whether the route's agent is waiting on its inbox right now.
- `diffs`: word-diff markup for diff items (`"<id>"`) and diff blocks (`"<id>/body/<n>"`), drawn by `diff.py`.

`render.js` polls this every 10 seconds with `If-None-Match` and redraws only on a new version.

### Answering

```bash
curl -s -X PUT -H 'Content-Type: application/json' \
  -d '{"base": 1, "answers": {"s1": {"answer": "yes", "note": ""}, "s2": {"answer": "changes", "note": "Name it"}}}' \
  http://127.0.0.1:8000/_page/demo/try/answers
```

Send only the items this tab changed. Each one is merged into the open round under the page lock, stamped with
`by` (the owner in `site.json`) and `at`, and its earlier answer moves into `was`. A stale `base` is fine: the
merge is item by item, so two tabs never undo each other. Answers are `yes`, `no`, `changes` and `skipped` as
the item allows, a choice's value, or free text for a question; `""` clears.

### Sending

```bash
curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"kind": "send", "results": "Review: Try it (/demo/try)"}' \
  http://127.0.0.1:8000/_page/demo/try/send
ls _inbox/ops/
```

A Send records the submission on the page, then writes one file to the route's inbox, atomically. `items`
defaults to every item answered in the open round; a blocker sends exactly one. The answers and notes come
from the page file, not from the request. A route whose `mode` is `copy` answers `409`: that page copies its
results instead.

The bar then shows where the latest Send or Blocker stands, from `submissions`, `listening` and the thread:
sent, picked up once the agent moves the file to `taken/`, the agent's newest reply after it, or, while nobody is
listening, "isn't listening." with a Copy results button.

## The inbox

```text
_inbox/<agent>/<prio>-<UTC stamp>-<folder>-<slug>-<n>.json      prio: 0 = blocker or restart, 5 = send
```

File names sort blockers first. Each file is one submission:

```json
{"schema": "handoff.submission/v1", "n": 1, "kind": "send", "page": "demo/try",
 "url": "http://127.0.0.1:8000/demo/try", "title": "Try it", "build": null, "round": 1, "rev": 3,
 "at": "2026-10-26T08:21:10-04:00",
 "items": [{"id": "s1", "n": 1, "answer": "yes", "note": "", "blocker": false},
           {"id": "s2", "n": 2, "answer": "changes", "note": "Name it", "blocker": false}],
 "results": "Review: Try it (/demo/try)"}
```

- **Waiting:** `page.py wait <agent>` blocks until a file is there and prints the waiting files, blockers first.
  While it runs it keeps its pid in `_inbox/<agent>/.listening`; the page shows the agent as listening only
  while that process is alive.
- **Taking:** move a file to `_inbox/<agent>/taken/`. The next read of the page records it as picked up, and
  the bar says so.
- **Answering:** reply on the page with `page.py reply <page> <id> --from <agent> "..."`, with `--action` for
  `filed`, `fixed`, `reopen`, `unblock`, `wontfix` or `info`. That reply is what the owner sees.
- **Missed wake-ups:** nothing is lost, because the files stay until they're taken. `page.py hook <agent>`
  prints one line whenever files are waiting or nothing is listening.

## The index

`GET /_index/<folder>` returns `{"folder", "name", "blurb", "pages"}`, and `GET /_index/` returns
`{"title", "folders": [...]}` with the same cards per folder. A card has `href`, `title`, `note`, `state`,
`chips`, `open`, `tally`, `priority`, `mtime`, `first` and, for a page file, `kind`. Page files and the HTML
pages in `_status.json` are merged in the index's order. The folder and root index pages themselves
(`/<folder>/`, `/`) are built from the same cards on request whenever page files are involved.

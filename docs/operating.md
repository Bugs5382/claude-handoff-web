# Operating the site

## Working memory, never committed

Install by copying the template into a working folder; the working folder is scratch memory and is never
committed. When a Claude agent (or any agent) runs an instance, it never creates a git repository for it:
pages change too often. Three guards back this up:

- `install.sh` refuses a target inside a git work tree and never runs `git init`;
- `serve.py` refuses to start when the served folder is inside a git work tree;
- every instance carries `CLAUDE.md` and `AGENTS.md` saying so.

This repository holds only the generic template and the fake `example/`. Never copy a live page,
`_status.json` or `_saved/` into it; `.gitignore` keeps `_saved/`, `_old/` and every `_status.json` outside
`example/` out.

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

## Endpoints

| Method | Path | What |
|---|---|---|
| `GET` | any static path | files, like `python3 -m http.server`; `_saved/` is never served |
| `GET`, `PUT` | `/_save/<name>.json` | answers (see `_site/SAVE-API.md`) |
| `POST` | `/_stale` | `{folder, page}`: Stale |

Nothing else is writable. `Cache-Control: no-store` is sent on `/_save/`, `.html` files and folder URLs.

## Stale

The owner's "Stale: remove this page" button (on needs-you cards and on unified review groups) deletes the
page for good after a confirm. The server only accepts a page that is listed in that folder's
`_status.json` and lies inside that folder: never `_site/`, `_old/`, a folder root, `review/` or a
`protected` page. It then marks the entry `done` with `Stale (<owner>, <date> <tz>)`, appends a line to
`_saved/stale-log.json`, and reruns the folder's builder and `gen-index.py`. Copy results on the unified page
lists recent ones as `STALE: <page>`.

## _old/ pruning

Before replacing a file, copy it to its folder's `_old/`. The server deletes files under any `_old/` folder
older than `prune_old_days` (default 7) once an hour and lists them in `_saved/prune-log.json`. Set
`"prune_old": false` to keep everything.

## Restarting

Stop the old process and start the new one straight after, so the gap is a fraction of a second:

```bash
kill <old-pid>; nohup python3 -u _site/serve.py --directory . >> server.log 2>&1 &
```

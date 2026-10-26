# Page files

A page file is one JSON file per page, `<folder>/<slug>.json`, in the `handoff.page/v1` format. It holds the
page definition, every round of answers with who and when, and a reply thread per item. The full design is in
`docs/design/json-pages.md` in the repo.

This first part is the file format and the one module that writes it. The server endpoints, the `page.py`
command line and the renderer come next; until then, HTML pages work as they always have.

## Before you start

- Python 3.10 or newer. Both modules are standard library only.
- Run them from `_site/` (or put `_site/` on `sys.path`): `pagefile.py` imports `schema.py`.

## The format

The definition keys sit at the top level, and the server keys are managed by `pagefile.py`.

| Key | Written by | Meaning |
|---|---|---|
| `schema` | definition | always `handoff.page/v1` |
| `kind` | definition | `review`, `checklist`, `journey`, `backlog`, `questions`, `reference` or `status` |
| `title`, `summary` | definition | the heading and the line under it |
| `build`, `reset` | definition | the build under test and a reset counter; changing either opens a new round |
| `status` | definition | the index card: `{"state": "needs-you", "note": "...", "chips": [...], "priority": 20}` |
| `options` | definition | a backlog's choices: `{"choices": [{"value": "start", "label": "Start"}, ...], "default": "hold"}` |
| `items` | definition | the content, in order |
| `route` | operator | `{"to": "ops", "mode": "send"}`; set with `set_route`, never in a definition |
| `rev` | server | 1 on create, up by 1 on every write |
| `rounds` | server | every round of answers, numbered from 1 |
| `thread` | server | replies per item id (and `_page`), numbered from 1 per item |
| `submissions` | server | every Send and Blocker |

Each kind gives items a default type: `review` uses `section`, `checklist` uses `check`, `journey` uses
`step`, `backlog` uses `choice`, `questions` uses `question`, and `reference` and `status` use `info`.
`reference` and `status` pages hold `info` items only. A `checklist` needs a `build`, and a `backlog` needs
`options`.

### Items

Every item has an `id` (`a-z`, `0-9`, `_` and `-`, up to 41 characters, unique on the page) and a `title`.
Answers are keyed by id, so reordering items never moves an answer.

| Type | Answers | Extra fields |
|---|---|---|
| `section` | Yes / No / Changes | `body` |
| `check` | adds Skipped | `body`, `howto`, `dependsOn`, `blockedBy` |
| `step` | adds Skipped | `steps`, `checkpoint`, `howto`, `dependsOn`, `blockedBy` |
| `screen` | Yes / No / Changes | `images` (`[{src, alt, caption}]`), `fields` (`[{name, type, rule}]`), `body` |
| `contract` | Yes / No / Changes | `fields`, `forms` (`[{name, fields}]`), `body` |
| `diff` | Yes / No / Changes | `old`, `new`, `code` |
| `question` | free text | `body`, `suggested` |
| `choice` | the page's `options` | `body` |
| `info` | none | `body` |

Answerable items also take `answers` (their own set, such as `["yes", "no"]`), `skip: true` (adds Skipped),
`dependsOn` (ids on the same page) and `blockedBy` (free text), and any item can take `section`, a group
heading.

### Body blocks

`body` and `howto` are lists of blocks, each with exactly one of these keys:

| Block | Shape |
|---|---|
| `p` | `{"p": "text"}`, inline `**bold**`, `*em*`, `` `code` `` and `[text](url)` only |
| `list`, `olist` | `{"list": ["a", "b"]}` |
| `code` | `{"code": "...", "lang": "sh"}` |
| `image` | `{"image": "img/a.png", "alt": "...", "caption": "..."}`, a file next to the page, never a `data:` URI |
| `table` | `{"table": [["h1", "h2"], ["a", "b"]]}`, the first row is the header |
| `diff` | `{"diff": {"old": "...", "new": "...", "code": false}}` |
| `copy` | `{"copy": "text"}` |
| `note` | `{"note": "text", "tone": "warn"}`, tone `info`, `warn`, `ok` or `danger` |
| `html` | `{"html": "..."}`, an escape hatch for content nothing else fits |

## Checking a file

```bash
python3 _site/schema.py app/design.json
```

It prints one error per line and exits 1 when there are any. Each error gives the JSON path: items by id,
and every other list by position counted from 1.

```text
items[c1].steps: expected a list of strings
items[s2].body[#3].tone: expected one of info, warn, ok, danger
```

## Writing a file

Only `pagefile.py` writes page files. Every write locks `<slug>.json.lock`, validates the result, writes a
temp file and renames it into place, so two writers never lose each other's changes. A page larger than 2 MB
is refused.

| Call | What it does |
|---|---|
| `write_definition(path, definition)` | creates the page (rev 1, round 1), or replaces its definition; a `build` or `reset` change closes the round and opens the next |
| `save_answers(path, {id: {answer, note}}, by=..., base=rev)` | merges one tab's changed answers into the open round, item by item; stamps `by`, `at` and the item's hash, and keeps earlier values in `was` |
| `new_round(path, results=...)` | Save round now: closes the round with its Copy results text and opens the next |
| `restart(path, checkpoint, by=...)` | restarts a journey from a checkpoint already reached: the steps up to it carry over as Yes, later steps start open |
| `reply(path, id, frm, text, action=..., reason=..., ref=...)` | appends a reply under an item or `_page`; `action="reopen"` reopens the item |
| `set_route(path, to, mode)` | the operator's route for the page |
| `item_states(doc)` | where each answerable item stands: its answer, whether an earlier Yes hides it, and why it reopened |

```python
import pagefile

pagefile.write_definition("app/design.json", {
    "schema": "handoff.page/v1", "kind": "review", "title": "Design",
    "items": [{"id": "s1", "title": "Purpose", "body": [{"p": "Why we need it."}]}],
})
pagefile.save_answers("app/design.json", {"s1": {"answer": "yes", "note": ""}}, by="Alex")
```

Answers are checked against the item: a value outside its set, Changes without a note, or an unknown id
raises `PageError`, whose `errors` list says which item and why.

### Rounds

- A round opens when the page is created, when `build` or `reset` changes, on Save round now and on Restart.
  Only the last round is open.
- A Yes from an earlier round hides the item in the new round.
- An item comes back open when a reply reopens it, or when its definition changes after its last Yes
  ("changed since round N"). A reopen nobody has answered carries into the next round.
- A Yes on a step with a `checkpoint` records the time the checkpoint was reached.

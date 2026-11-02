# Page files

A page file is one JSON file per page, `<folder>/<slug>.json`, in the `handoff.page/v1` format. It holds the
page definition, every round of answers with who and when, and a reply thread per item. The full design is in
`docs/design/json-pages.md` in the repo.

This covers the file format, the one module that writes it, the `page.py` command line for agents, the
server endpoints that read and write it (listed in `docs/operating.md` in the repo), and the renderer that
draws it. HTML pages keep working as they always have.

## Before you start

- Python 3.10 or newer. Both modules are standard library only.
- Run them from `_site/` (or put `_site/` on `sys.path`): `pagefile.py` imports `schema.py`.

## Viewing a page

A page file is shown at `/<folder>/<slug>`. The server answers with `_site/app.html`, and the React app in `_site/app/` (built from `web/` in the repo)
draws the page from `GET /_page/<folder>/<slug>` into the same markup an HTML page uses, so `site.css` and
`review.js` work unchanged:

- each answerable item is a numbered card (`<section data-review-question>`), and `info` items are plain
  sections;
- each item answers its own way, so one page can mix them: a section takes Yes / No / Changes (or its own
  `answers` set), a check or step adds Skipped, `skip: true` adds Skipped to that item only, a choice uses the
  page's `options` and default, and a question takes free text;
- the page's settings become the body attributes `review.js` reads: the build, what's blocked (an unmet
  `dependsOn`, or a `blockedBy` with no `unblock` reply), the earlier-round Yes items to hide, and the reopened
  items with their reasons;
- how-tos become `<template data-howto>`, pictures open in the picture pop-out, and diff items and blocks
  are drawn by the server with `diff.py`, with the Diff | Final switch;
- `reference` and `status` pages have no answer bar.

The app saves through `PUT /_page/.../answers` (, only the items this tab changed), and
History lists the page's closed rounds. When the page's route sends, Blocker becomes "Blocker: send now" and
the bar gains "Send to <agent>" with the latest send's delivery state: "Sent 07:42", "Picked up by app 07:43",
"app replied 07:50: ..." (a link to the page's replies), or "app isn't listening." with a Copy results instead
button. A journey shows "Restart from a checkpoint" with one button per checkpoint reached; picking one asks
first, on the page, and once restarted the restart shows its own delivery state. Under each item, a thread lists
my answers from earlier rounds and the agents' replies, oldest first, with who, the round, when, and a tag for
Filed, Fixed, Reopened (with the reason), Unblocked and Won't fix; past four entries the oldest fold behind
"Show N earlier". Replies about the whole page (`_page`) sit in their own card at the top.

The page polls every 10 seconds and redraws in place when the file changes: never while the owner is typing, within
3 seconds of a click, or while answers are still unsaved, and it keeps the scroll position. When the only
change is this tab's own answers coming back, it doesn't redraw.

## On the index

A page file is its own index card; it needs no `_status.json` entry. The card follows the same rules as an HTML
page's: it sorts by `status.priority`, then by the number in its title or slug; it shows the open count (or a
backlog's per-choice counts), To review, Reopened and Approved, the Reference or Done chip, and `status.chips`.
It stays in Needs you until every counted item is Yes, unless `status.state` says otherwise. Stale marks it done
and moves the file to `<folder>/_old/`. Its closed rounds are listed on `/<folder>/history/` with their Copy
results text.

## The format

The definition keys sit at the top level, and the server keys are managed by `pagefile.py`.

| Key | Written by | Meaning |
|---|---|---|
| `schema` | definition | always `handoff.page/v1` |
| `kind` | definition | `review`, `checklist`, `journey`, `backlog`, `questions`, `reference`, `status` or `round` |
| `title`, `summary` | definition | the heading and the line under it |
| `build`, `reset` | definition | the build under test and a reset counter; changing either opens a new round |
| `status` | definition | the index card: `{"state": "needs-you", "note": "...", "chips": [...], "priority": 20}` |
| `options` | definition | a backlog's choices: `{"choices": [{"value": "start", "label": "Start"}, ...], "default": "hold"}` |
| `items` | definition | the content, in order |
| `phases` | definition | a round's phases: `[{"id": "A", "title": "...", "goal": "...", "dependsOn": ["A"]}]`; item ids become `A1`, `A2`, `B1` |
| `deck` | definition | `true` adds Build a deck to the bar's More menu |
| `template` | definition | a template from `custom/custom.js`, see `CUSTOM.md` |
| `drafts` | definition | `true` adds Draft email to every item |
| `emails` | server | versions of each item's email, numbered from 1 |
| `revisions` | server | each item's earlier definitions: `{"at", "round", "before", "after"}` |
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

### Generating an email

Use this when someone outside the page needs telling: an inventory step was re-verified and the data changed, so the network team needs to know what's different, or some devices couldn't be reached, so a note goes to whoever can grant access.

With `"drafts": true`, every item has Generate an email in its More button, whatever its answer. The person says who it's to, what they need from them, and the tone. That goes to the agent's inbox the same way as a Send, as a submission of kind `email`, with a `context` holding the step: its title and body, what changed between rounds, and the comments and replies, so the person doesn't retype any of it. It doesn't answer the item or lock it.

The agent answers with `page.py email`. The email appears in the step as To, Subject and Body, each with a copy button, as a new version. Earlier versions stay readable. Change this asks for another version, sending `change` and `basedOn`.

### Building a deck

With `"deck": true`, the bar's More menu has Build a deck, which runs only when it's pressed. It asks what the person is trying to build, and sends that as `framing` in a submission of kind `deck`. The deck's content is only the items whose final answer is Yes or Accept risk, each with its title, body and note. It locks nothing. The agent builds the deck, saves it beside the page and replies with the link, such as `page.py reply app/plan _page --from app "[The deck](/app/plan-deck.pptx)"`. On a page that only copies, the button copies the same content instead.

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

## Sample pages

`_site/samples/` holds one sample of every page kind, including pages part-way through a round: a Blocked by, a
reopened item, a handled Changes and a part-sent page. All the data is made up. `page.py samples <folder>` loads
them, and running it again puts them back as they were, without touching any other page in the folder.

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

## The command line

Agents use `page.py`; it writes through `pagefile.py`, so it takes the same lock. A page is named
`<folder>/<slug>`, and `--root` sets the site folder (the default is the folder above `_site/`).

| Command | What it does |
|---|---|
| `page.py new app/design --from design.json` | creates a page (the definition comes from stdin without `--from`) |
| `page.py set app/design --from design.json` | replaces the definition; a `build` or `reset` change opens a round |
| `page.py reply app/design s1 --from app --reopen "fixed in #70" "Fixed in #70."` | a reply under an item, or `_page`; `--action` takes `filed`, `fixed`, `reopen`, `unblock`, `wontfix` or `info`, with `--reason` and `--ref` |
| `page.py status app/design done --note "Shipped" --chip Shipped --priority 10` | the index card |
| `page.py route app/design --to app --mode send` | the page's route (the operator's call) |
| `page.py round-close app/design --results "..."` | Save round now |
| `page.py check app/design` | validates a page or a `.json` file; errors give the JSON path, exit 1 on any |
| `page.py wait app` | blocks until a submission is in `_inbox/app/`, prints the files (blockers first) and exits |
| `page.py hook app` | prints one line when the inbox has untaken files or nothing is listening |
| `page.py email app/design s1 --from app --request 4 --subject "Why" "Dear team,..."` | an email comes back as the next version on that item; `--request` is the submission that asked, so the version keeps who it's to and what was asked |
| `page.py samples demo --route app` | loads the sample pages into a folder as `sample-*`; run it again to reset them |
| `page.py convert app/design.html` | turns a review.js page into a page file next to it (`--print` shows the definition only) |

### Waiting for submissions

Run `page.py wait <agent>` as a background command and act when it exits:

1. Read the files it printed, blockers first.
2. Take each one by moving it to `_inbox/<agent>/taken/`; the page then shows it as picked up.
3. Do the work and answer with `page.py reply`.
4. Start `page.py wait <agent>` again.

It exits at once when files are already waiting, and waits about 200 ms after the first file so a Send and a
Blocker that land together are both listed. While it runs it keeps its pid in `_inbox/<agent>/.listening`, so
the page can say whether the agent is listening. It uses kqueue where there is one, and otherwise checks the
folder every 2 seconds (`--poll` forces that). `--timeout S` gives up after S seconds with exit code 3.

`page.py hook <agent>` is for a hook that runs whenever the agent is next spoken to: it stays quiet while the
agent is listening and its inbox is empty, and otherwise prints one line saying what to do.

### Converting an HTML page

`page.py convert <folder>/<page>.html` maps a review.js page to a page file beside it and leaves the HTML in
place, so both can be checked side by side:

- each `<h2>` becomes an item `s1`, `s2` and so on, and on a `data-review-h2="off"` page each
  `[data-review-question]` section becomes an item with its own id in lower case, so saved answers still match
  (two ids that differ only by case stop the convert);
- a page that doesn't load `review.js` becomes a `reference` page;
- `data-build`, `data-review-reset`, `data-review-options` and `data-review-default`, `data-review-skip`,
  `data-review-blocked` (a dependsOn when it names an item, else a blockedBy), question items and
  `<template data-howto>` carry over, and the folder's `_status.json` entry becomes `status`;
- paragraphs, lists, code, pictures, tables and `.rvdiff` blocks become blocks; a table with merged cells and
  anything else is kept as a flagged `html` block and named on stderr;
- the saved answers (`_saved/<page-key>.json`) become the open round and the round history files become
  closed rounds, with their numbers kept;
- a `data-review-approved` item counts as Yes, and one that was already Yes in the last closed round stays
  hidden, as it was on the HTML page;
- a `data-review-reopen` item is reopened, unless it was answered again since; then the reason becomes an
  `info` reply from the operator under the item.

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
| `set_status(path, state, note=..., chips=..., priority=...)` | the index card |
| `add_submission(path, record)`, `mark_taken(path, n)` | record a Send, Blocker or Restart, and its pick-up |
| `item_states(doc)` | where each answerable item stands: its answer, whether an earlier Yes hides it, and why it reopened |
| `summary(doc)` | the bar's counts: open, blocked, Yes, reopened, approved, and a backlog's per-choice tally |

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
- A Yes from an earlier round stays on the page as a collapsed row with Yes pressed and locked. Show opens the row.
- A Send locks the items it carried, and a banner says where it stands: in the agent's inbox, nobody listening, or
  picked up. Everything else stays open, and a later Send carries only what's new. The agent's next `page.py set`
  or `reply` unlocks them live, in the same round, and every Yes that Send carried is
  then a locked row and stays in Copy results. "Unlock to change an answer" takes the lock off sooner and takes that
  Send back, so its answers can change.
- A sent No or Changes clears once the agent replies under the item or changes it. It moves to the round's `handled`
  list, so an old note can't go out again, shows in the item's thread with what the agent did, and the item is open
  again marked "Updated: answer again". A reply about the whole page clears nothing.
- An item comes back open when a reply reopens it, or when its definition changes after its last Yes
  ("changed since round N"). A reopen nobody has answered carries into the next round. A reopened Yes shows
  unanswered, and one Yes clears it.
- A Yes on a step with a `checkpoint` records the time the checkpoint was reached.

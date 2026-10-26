# JSON pages: one file per page, one renderer, answers sent to an agent

Status: design, waiting for my approval. Nothing here is built until it's approved. Tracking issue: #52.

## 1. Intent

Today every page is hand-written HTML that loads `review.js`. The rest of the page's data is spread out:
- the answers live in `_saved/<key>.json`;
- past rounds live in `_saved/history/<key>/`;
- the folder index reads `_status.json`;
- what an agent did about an answer lives only with that agent, or in a comment somewhere else.

Results reach an agent when I press Copy results and paste them.

I want that to be one thing. Each page is one JSON file holding three things:
- the page itself;
- every round of my answers, with who and when;
- a reply thread per item, where agents say what they did.

One renderer draws every page type from that file. When I finish, the results are either copied or sent
straight to an agent session, whichever the operator set for that page.

## 2. Goals

1. **One file per page.** The definition, every round of answers and every item's replies live in one JSON
   file. Nothing is overwritten: a changed answer keeps the earlier one, and a closed round is never edited.
2. **One renderer for every page type:**
   - design and section reviews, and re-review rounds;
   - contract and screen reviews with screenshots;
   - sign-off checklists;
   - test journeys with checkpoints;
   - open questions;
   - a backlog's Start / Hold;
   - reference pages.

   No more hand-written HTML pages.
3. **A schema the server enforces.** A page file that doesn't match is refused with a message that says what
   is wrong and where. The agent finds out when it writes the file, not when I open the page.
4. **Today's behaviour carries over.** That covers:
   - Yes / No / Changes, a note required for Changes, and Skipped (locked) on checklists;
   - the Blocker button and the jump bar (Next and Previous open item, open-ID chips, the n and p keys);
   - the bottom bar's states;
   - live updates without a reload, never while I'm typing;
   - Stale and the chips;
   - approved items hidden in later rounds, and reopened items with their reason;
   - Mark unanswered Yes / No and the Diff | Final switch;
   - the picture pop-out;
   - Copy results, light and dark themes, and saving on the server.
5. **Results go to an agent without copy and paste.** The server writes each submission into the target
   agent's inbox, and the agent is woken when it arrives, with no polling loop on the agent's side. Blockers
   jump the queue.
6. **Indexes come from the page files.** A folder index and the root "Needs you now" list are worked out
   from the JSON files themselves. Converted pages don't need `_status.json` or a `gen-index.py` run.
7. **Numbering always starts at 1:** items, steps, rounds, checkpoints, thread replies and submissions.

## 3. Non-goals

- **No multi-user editing or sign-in.** The site stays one owner on 127.0.0.1. "Who" means the owner (`owner` in
  `site.json`) or a named agent.
- **No database.** Pages stay files on disk with atomic writes, as today.
- **No new runtime dependencies.** `serve.py` stays standard-library Python, and the renderer stays plain
  JavaScript with no build step.
- **No WYSIWYG page editor.** Agents write JSON and I answer.
- **No unified `/<folder>/review/` aggregator.** Each review lives only on its own page. `build-review.py` and
  the "(c) Unified review page" type are retired, not converted.
- **The server never drives an agent.** It only writes to an inbox folder. What the agent does with a
  submission is up to the agent.

## 4. Anti-goals: what would make this a failure even if it works

- **A lost or silently overwritten answer.** Several things can write to a page: my browser, an agent adding a
  reply, an agent updating the page. None of them may ever clobber another.
- **A submission that vanishes.** If no agent is listening, the page must say so, and Copy results must still
  work.
- **A delivery path that depends on an agent runtime's undocumented internals.**
- **A page that redraws under me while I'm typing,** or jumps me to the top.
- **A rewrite that drops features the site already has.** The parity list in section 11 is a gate, not a wish
  list.

## 5. Constraints

- **A running site stays up through the change.** Old HTML pages keep working until each one is converted.
- **Page files are working memory, never committed.** `serve.py` already refuses to serve from inside a git work
  tree, and that stays. Only `example/` pages live in this repo.
- **The test stack stays the same:** pytest, ruff and mypy, plus the headless Chrome smoke harness
  (`tests/js/review_smoke.html`).
- **Pictures stay as files next to the page** (`img/`). A page file references them by path and never embeds
  them.

## 6. The page file

### 6.1 Where it lives and how it's reached

- **File:** `<folder>/<slug>.json`, or deeper, such as `app/journeys/new-laptop-order.json`. A slug is
  `[a-z0-9][a-z0-9-]{0,80}`.
- **URL:** `/<folder>/<slug>`, with no extension. The server answers with one shared renderer shell
  (`_site/page.html`), which fetches `/_page/<folder>/<slug>` and draws the page. The old `.html` URL of a
  converted page redirects to the new one.
- **One writer module:** only `_site/pagefile.py` touches a page file. Two things call it:
  - the server, for my answers, Stale and submissions;
  - the `_site/page.py` command line, for agents writing the definition, replies, routing and status.
- **Locking:** every write takes an exclusive lock (`fcntl.flock` on `<slug>.json.lock`), reads, validates,
  changes, writes a temp file and renames it into place. So the browser and an agent can never clobber each
  other.
- **No hand edits:** agents never edit the file by hand. Locking only works if every writer goes through the same
  door.

### 6.2 Top-level shape (`handoff.page/v1`)

The definition keys sit at the top level. The server manages `rev`, `rounds`, `thread` and `submissions`. A
definition write that touches them is refused.

```json
{
  "schema": "handoff.page/v1",
  "rev": 14,
  "kind": "journey",
  "title": "Journey 1: New laptop order",
  "summary": "Order a laptop end to end, from install to delivery.",
  "build": "example-app 8feb547",
  "reset": 2,
  "status": { "state": "needs-you", "note": "Round 2 after the warranty fix.", "chips": ["Reopened"], "priority": 20 },
  "route": { "to": "app", "mode": "send" },
  "options": null,
  "items": [ ... ],
  "rounds": [ ... ],
  "thread": { "c1": [ ... ] },
  "submissions": [ ... ]
}
```

| Key | Who writes | Meaning |
|---|---|---|
| `schema` | agent | always `handoff.page/v1`; a future v2 is a migration, not a silent change |
| `rev` | server | goes up by 1 on every write; it's the renderer's change signal and the browser's merge base |
| `kind` | agent | `review`, `checklist`, `journey`, `backlog`, `questions`, `reference` or `status` (6.3) |
| `title`, `summary` | agent | the heading and the line under it; the title is also the index card's title |
| `build` | agent | the build under test (today's `data-build`); a change opens a new round |
| `reset` | agent | an integer; bumping it opens a new round without a new build (today's `data-review-reset`) |
| `status` | agent | the index card: `needs-you`, `reference` or `done`, plus a note, chips and a priority (section 9) |
| `route` | operator | where Send goes: `to`, an agent name that defaults to the operator, and `mode`, which is `send`, `copy` or `both` (section 8) |
| `options` | agent | a backlog's own choices, such as `[{"value": "start", "label": "Start"}, ...]` with `"default": "hold"` |
| `items` | agent | the content, in order (6.4) |
| `rounds` | server | every round of my answers (section 7) |
| `thread` | anyone, append-only | the replies per item id (7.4) |
| `submissions` | server | every Send and Blocker, with its delivery state (section 8) |

### 6.3 Kinds

A kind sets defaults so a page doesn't repeat itself. Any default can be overridden per item.

| Kind | Default item type | Answers | What it's for |
|---|---|---|---|
| `review` | `section` | Yes / No / Changes | design, plan, contract, screen and re-review pages; approved items from earlier rounds are hidden |
| `checklist` | `check` | Yes / No / Changes / Skipped | sign-off of delivered work; `build` is required, and each check has a how-to |
| `journey` | `step` | Yes / No / Changes / Skipped | ordered steps with checkpoints and restart from a checkpoint (6.5) |
| `backlog` | `choice` | the page's `options` | Start / Hold and the like; no approval and no Blocker |
| `questions` | `question` | free text | a page of open questions; never blocks anything |
| `reference` | `info` | none | hand-off notes, email drafts, "what's built"; no bar, live updates only |
| `status` | `info` | none | a live status page (today's type (h)); the agent rewrites it as things move |

Today's other page types map like this:

| Today's type | Becomes |
|---|---|
| (e) Decision page | a `review` whose items carry the options as content |
| (f) Walk-through or ASCII mock | a `review` with `code` blocks |
| (g) Hand-off note or email draft | a `reference` with a `copy` block |

### 6.4 Items

**Ids and numbers:**
- Every item has an `id` and a `title`.
- An id is `[a-z0-9][a-z0-9_-]{0,40}` and unique on the page. Once I've answered an item, its id never changes.
- The renderer numbers items 1, 2, 3 in page order. The number is for display only. Answers are keyed by `id`, so
  reordering never moves an answer to a different item.

| Type | Answerable | Extra fields |
|---|---|---|
| `section` | Yes / No / Changes | `body` (blocks) |
| `check` | adds Skipped | `body`, `howto` (blocks, opened in the pop-out), `dependsOn`, `blockedBy` |
| `step` | adds Skipped | `steps` (strings, shown as a numbered list), `checkpoint`, `dependsOn`, `blockedBy`, `howto` |
| `screen` | Yes / No / Changes | `images` (`[{src, alt, caption}]`), `fields` (a table of name, type, rule), `body` |
| `contract` | Yes / No / Changes | `fields`, `forms` (`[{name, fields: [...]}]`), `body` |
| `diff` | Yes / No / Changes | `old`, `new` and `code: bool`; the server renders it with `diff.py`, and the Diff / Final switch stays |
| `question` | free text | `body`, plus `suggested` for the "Use suggestion" button |
| `choice` | the page's `options` | `body`; the comment is optional |
| `info` | no | `body`; it isn't counted and isn't in the bar |

Fields shared by every answerable item:

| Field | What it does |
|---|---|
| `answers` | overrides the kind's set, such as `["yes", "no"]` |
| `skip: true` | adds Skipped (locked) outside checklists |
| `dependsOn` | ids that must be Yes in the current round before this item unblocks. It replaces the hand-written `data-review-blocked` and works itself out from the answers. |
| `blockedBy` | free text, such as `"example-org/app#70"`. The item stays blocked until an agent clears it. |
| `section` | a group heading drawn above the item |

**Body blocks** come from a small, fixed vocabulary, so the renderer stays simple and a page can't break the
layout:

| Block | Shape |
|---|---|
| `p` | `{"p": "text"}`. Inline markup only: `**bold**`, `*em*`, `` `code` ``, `[text](url)`; everything else is escaped. |
| `list` / `olist` | `{"list": ["a", "b"]}`; an `olist` always starts at 1 |
| `code` | `{"code": "...", "lang": "go"}`, with a Copy button inside a how-to |
| `image` | `{"image": "img/a.png", "alt": "...", "caption": "..."}`, opened in the shared pop-out |
| `table` | `{"table": [["h1", "h2"], ["a", "b"]]}`; the first row is the header |
| `diff` | `{"diff": {"old": "...", "new": "...", "code": false}}` |
| `copy` | `{"copy": "text"}`: a block with a Copy button, for email drafts |
| `note` | `{"note": "text", "tone": "warn"}`: a callout |
| `html` | `{"html": "..."}`: an escape hatch for content the converter can't map. The page flags it so it gets cleaned up. |

### 6.5 Journeys: steps, checkpoints and restart

**Checkpoints:** a step with `checkpoint: "system-ready"` marks that checkpoint as reached when I answer the step
Yes. The server records the time in `rounds[n].checkpoints`.

**Restart from a checkpoint.** The page shows "Restart from:" with one button per checkpoint reached so far. When
I pick one:
1. The server closes the current round and opens a new one.
2. The steps up to and including that checkpoint carry over as Yes. Later steps start open.
3. It sends a `restart` submission to the page's route.
4. The agent resets the environment (restores the snapshot, or reseeds) and replies in the thread when it's
   ready.

**Order:** `dependsOn` works as it does on checks. By default a step depends on the one before it, because a
journey runs in order. A step can opt out with `"dependsOn": []`.

## 7. Rounds and history

### 7.1 A round

```json
{
  "round": 2,
  "build": "example-app 9a1c0de",
  "reset": 2,
  "opened": "2026-10-26T08:05:44-04:00",
  "closed": null,
  "openedBy": "build changed",
  "answers": {
    "c1": {
      "answer": "yes", "note": "", "by": "Alex", "at": "2026-10-26T08:20:02-04:00",
      "was": [ { "answer": "changes", "note": "Laptop type is missing a warranty field", "at": "2026-10-26T07:42:10-04:00" } ]
    }
  },
  "checkpoints": { "after-install": "2026-10-26T08:20:02-04:00" }
}
```

**The round list:**
- `rounds` is append-only and numbered from 1. The last round has `closed: null`, and it's the only one that
  changes.
- An answer I change keeps its earlier values in `was`, oldest first, so nothing is overwritten. A cleared
  answer is recorded as an entry with `answer: ""`.

**When a round opens:**
- a definition write changes `build` or `reset` (`openedBy` says "build changed" or "reset");
- I press Save round now;
- I pick Restart from a checkpoint.

Closing a round stamps `closed` and stores that round's Copy results text in `results`.

**Carried over automatically:**
- An item I answered Yes in an earlier round is hidden in the new one and stays in Copy results. This replaces
  the hand-written `data-review-approved` list.
- An item comes back when it's reopened (7.3) or when its content changes. The server keeps a hash of each item's
  definition per round, and a changed hash reopens the item with the reason "changed since round N".

**History view:**
- The collapsed History block at the bottom of a page reads straight from `rounds`.
- Converted pages need no separate `_saved/history/`.
- `/<folder>/history/` lists every page's rounds from the files.

### 7.2 Answers from the browser

The browser sends `PUT /_page/<folder>/<slug>/answers` with `{"base": <rev>, "answers": {id: {answer, note}}}`.
The body holds only the items this tab changed. Under the lock, the server:
1. merges them into the open round;
2. stamps `by` and `at`;
3. moves the earlier values into `was`;
4. bumps `rev` and returns it.

This is today's merge rule (the server copy, with every item this tab changed laid over it), now done in one
place. Everything else in SAVE-API.md carries over: the debounce, retry with backoff, "Not saved, retrying" and
the `beforeunload` keepalive save.

### 7.3 Reopen

A reopen is a thread reply with an action, so the reason and who reopened the item are recorded once. For
example:

```bash
page.py reply app/journeys/new-laptop-order c1 --from app --reopen "fixed in #70" "Fixed in #70 (warranty end date on Laptop)."
```

The server marks `c1` "Reopened: fixed in #70" in the open round. The renderer shows the pill, and the item
counts as open again even if it was Yes.

### 7.4 The reply thread

```json
"thread": {
  "c1": [
    { "n": 1, "from": "ops", "at": "2026-10-26T07:43:02-04:00", "round": 1,
      "text": "Filed example-org/app#70; restart from after-install once it lands.", "action": "filed", "ref": "example-org/app#70" },
    { "n": 2, "from": "app", "at": "2026-10-26T08:05:44-04:00", "round": 1,
      "text": "Fixed in #70. Reopened c1.", "action": "reopen", "reason": "fixed in #70" }
  ]
}
```

- **Append-only:** replies are numbered from 1 per item.
- **Actions:** `action` is `filed`, `fixed`, `reopen`, `unblock`, `wontfix` or `info`, or it's left out. `unblock`
  clears a `blockedBy`.
- **What I see:** under each item, the renderer interleaves my answers from every round with the replies, oldest
  first.
- **Page-level replies:** the key `_page` holds replies about the whole page, such as "all fixed, round 3 is
  ready".

## 8. Routing and delivery

### 8.1 What I see

- **Copy results** stays in the bar and always works.
- **Send to \<agent\>:** when the page's `route.mode` is `send` or `both`, the bar also shows a Send button. It
  turns green once every open item is answered, like the bar today. I can still send a partial result; it asks
  first.
- **Blocker: send now** on an item sends that one item at once, ahead of everything else. When the mode is
  `copy`, the button stays "Blocker: copy now" and copies, as today.
- **Delivery state:** after a send, the bar shows it from `submissions`:
  - "Sent 07:42";
  - "Picked up by app 07:43";
  - then the agent's reply when it arrives.

  When nobody is listening, it says "app isn't listening. Copy results instead?" and offers Copy results.

### 8.2 Who sets the route

The operator sets the route, not the agents:
- **Default:** a `route` per folder in `site.json` (`{"to": "ops", "mode": "send"}`). Without one, the
  route is the operator's folder.
- **Per page:** `page.py route <page> --to app --mode send` overrides the default.
- **Agents** only add replies. They never change the route.

### 8.3 The inbox

The server writes each submission as one file, atomically:

```
_inbox/<agent>/<prio>-<UTC stamp>-<folder>-<slug>-<n>.json      prio: 0 = blocker or restart, 5 = send
```

```json
{ "schema": "handoff.submission/v1", "n": 3, "kind": "send",
  "page": "app/journeys/new-laptop-order", "url": "http://127.0.0.1:5390/app/journeys/new-laptop-order",
  "title": "Journey 1: New laptop order", "build": "example-app 9a1c0de", "round": 2, "rev": 14,
  "at": "2026-10-26T08:21:10-04:00", "items": [ {"id": "c2", "n": 2, "answer": "changes", "note": "...", "blocker": false} ],
  "results": "<the Copy results text, in its unchanged format>" }
```

- **Order:** file names sort blockers first, so an agent that reads them in order handles blockers first.
- **Taking a file:** an agent takes a submission by moving it to `_inbox/<agent>/taken/`. The server then
  records "picked up" on the page.
- **Finishing:** the agent finishes with a reply on the page (`page.py reply ...`), and that reply is the answer
  I see.
- **Nothing is deleted:** `taken/` is kept and pruned like `_old/`.
- **Not served:** `_inbox/` is never served, the same as `_saved/`.

### 8.4 How an agent wakes up

What an agent runtime offers varies, so the design needs only one capability: the agent can start a background
command and is told when it exits. Anything beyond that is optional.

| Path | Verdict |
|---|---|
| A background command that blocks until a file arrives, then exits | **Primary.** It costs the agent nothing while it waits, and the inbox stays durable if a wake-up is missed. |
| A push channel into the agent, where the runtime has one | **Later, optional.** Where it exists today it's experimental and needs extra launch flags, so it's not the default. |
| Agent-to-agent messaging | **Not used by the server.** Its wire format isn't a public interface. Agents can still forward to each other. |
| A file watcher run by the agent with a time limit | **Not primary.** It has to be restarted on a timer, and every restart costs the agent a turn. |
| Prompt hooks that run when the agent is next spoken to | **Safety net only** (point 4 below) |

**The design:**
1. **The wait command.** `page.py wait <agent>` blocks on the inbox folder. It uses `select.kqueue` on macOS
   and inotify on Linux, with a 2-second `os.scandir` fallback when neither is available. The fallback loop runs
   inside the script, so it costs the agent nothing.
   - When a file arrives, it prints the file names, blockers first, and exits.
   - If files are already waiting when it starts, it exits at once.
   - While it runs, it holds `_inbox/<agent>/.listening` with its pid.
2. **The agent's loop.** The agent runs the wait as a background command and is told when it exits. It then:
   1. takes the files;
   2. acts on them;
   3. replies on the page;
   4. starts the wait again.
3. **Listening state.** The server checks `.listening` (is the pid alive?). The page uses it to show
   "listening" or "not listening", and to offer Copy results when nobody is there.
4. **Safety net.** `page.py hook <agent>` prints one line when the inbox has untaken files or nothing is
   listening. It's meant for a hook that runs whenever the agent is next spoken to. So an agent that restarted,
   or lost its loop, re-arms the next time anyone talks to it. Nothing is lost in between, because the inbox is
   durable.
5. **Blockers.** The wait exits on any new file, and blocker files sort first. How fast an agent drops other work
   for a blocker is up to the agent's own instructions; the site doesn't enforce it.

**Spike first.** The first build step proves points 1 and 2 on a real machine in three cases:
- an idle agent;
- an agent in the middle of a task;
- an agent that was restarted.

If an idle agent isn't woken when its background command exits, the fallback is the safety-net hook, plus the
operator agent forwarding submissions. That fallback needs my decision before the build goes further.

## 9. Indexes from the page files

- **Built on request.** The server builds `/<folder>/` and `/` from the page files.
- **Order:** `status.priority`, then the number in the title or slug (1, 2, ... 10), then file order. That's
  today's ordering rule.
- **Card content:**
  - the title, `status.note` and chips;
  - New and Updated, from file times;
  - Reopened, when the open round has reopened items;
  - Approved, when every item is Yes;
  - `status.chips`;
  - the open count, or the per-choice counts on a backlog, worked out from the open round exactly as the bar
    counts.
- **State:** a page is `needs-you` while its open round has open items, unless `status.state` says otherwise. An
  agent sets `done` or `reference` with `page.py status`.
- **Stale** still marks the page done and logs it, but now it moves the file to `_old/` instead of deleting it.
- **Live:** the indexes are drawn by the same renderer (`kind: "index"`, fed by `GET /_index/<folder>`) and update
  live the way a page does.
- **During migration:**
  - The index merges converted pages with the folder's `_status.json` entries for pages still in HTML.
  - Once a folder has no HTML pages left, its `_status.json` moves to `_old/` and `gen-index.py` stops running
    for it.

## 10. The renderer and live updates

**Files:**
- `_site/page.html` is the shell: the head, the theme and an empty `main`.
- `_site/render.js` draws kinds, items and blocks into today's DOM and classes, so `site.css` keeps working.
- `_site/review.js` keeps the answer controls, the bar, the jump bar, notes, Blocker, Mark unanswered and the
  Diff | Final switch. It's refactored to take its items from `render.js` instead of scanning `h2`s and `data-*`
  attributes.
- `live.js` keeps index and page polling.

**Live updates:**
- The renderer polls `GET /_page/...` every 10 s with `If-None-Match: <rev>`. An unchanged page returns a cheap
  304.
- On a new `rev` it redraws in place. It keeps my unsaved typing, the scroll position, open pop-outs and the
  Diff / Final choice.
- It never redraws while I'm typing or just after a click, which is today's rule.
- There's no full reload any more, because the page is data.

**Validation:**
- `_site/schema.py` is a hand-written, standard-library validator for `handoff.page/v1`. `pagefile.py` runs it on
  every write.
- Errors give the JSON path and what was expected, such as `items[3].steps: expected a list of strings`.
- `page.py check <file>` runs the validator on its own.
- The renderer trusts the file, because the server already checked it.

## 11. Parity gate

Each of today's features needs a smoke scenario. The current scenarios in `tests/test_review_smoke.py` move to
JSON pages and must keep passing with the same meaning:
- Yes / No / Changes and notes;
- Blocker;
- the jump bar, the n and p keys, and the Open IDs picker with its filter;
- the bar's colour states and the "Back to folder" link;
- saved answers, and the amber "Not saved";
- Skipped (locked);
- hidden approved items;
- reopened items with their reason;
- blocked-by;
- open questions with "Use suggestion";
- backlog choices with a default;
- the theme;
- Copy results and Copy blockers;
- Mark unanswered Yes / No;
- Diff | Final;
- the picture pop-out;
- the how-to pop-out with Copy buttons;
- History and Save round now;
- Stale;
- the New and Updated chips;
- live updates without a reload.

Two changes are on purpose: the unified aggregator page is gone (section 3), and Stale moves the file to `_old/`
instead of deleting it.

## 12. Migration

The repo's code goes first, then any running sites.

**Phase 1: this repo.** One parent issue with ordered sub-issues, and one PR each:
1. **The spike** from 8.4. It's throwaway; the result is a report.
2. **`schema.py` and `pagefile.py`:** the schema, the validator, locking, rounds, the thread and the merge rules.
   Unit tests only.
3. **`serve.py`:**
   - the `/_page/` and `/_index/` endpoints;
   - the answer merge;
   - Stale on files;
   - the inbox writer and `.listening`;
   - the redirect from an `.html` URL to its slug.
4. **`page.py`:** the subcommands `new`, `set` (the definition), `reply`, `status`, `route`, `round-close`,
   `check`, `wait`, `hook` and `convert`.
5. **`render.js` and `page.html`,** plus the `review.js` refactor, with the parity smoke scenarios.
6. **Indexes and history from the files,** plus the merged index used during migration.
7. **Docs:**
   - page-types.md, rewritten with a JSON example per kind;
   - SAVE-API.md, replaced by the page and inbox API;
   - operating.md and `_site/README.md`;
   - `example/`, converted to JSON pages.

The old HTML path keeps working the whole time. `review.js` still runs HTML pages until phase 2 ends.

**Phase 2: a running site.** One folder at a time, with a backup taken outside the site first:
1. **Convert.** `page.py convert <page>.html` maps a review.js-structured page to a page file:
   - `h2`s and `[data-review-question]` sections become items;
   - the `data-*` attributes become `build`, `reset`, `dependsOn`, `blockedBy`, `options`, `skip` and question
     items;
   - `<template data-howto>` becomes `howto`;
   - `.rvdiff` blocks become `diff` blocks;
   - anything it can't map becomes a flagged `html` block.

   It also imports the page's saved answers (`_saved/<key>.json`) as the open round, and its history files as
   closed rounds, keeping their round numbers.
2. **Check, then keep the original.** Each converted page is checked side by side: the old HTML against the new
   render, with the same answers. Then the HTML goes to the backup, not to `_old/`, which prunes after 7 days.
3. **Generators.** Any scripts that generate pages switch to writing page files through `page.py`.
4. **Retire `_status.json`.** A folder's `_status.json` retires once its last HTML page is converted.

## 13. Testing

- **`schema.py`:** a valid and an invalid fixture for every kind, item type and block. The tests check that each
  error message gives the JSON path.
- **`pagefile.py`:**
  - two processes writing the same file at once: the lock holds and neither write is lost;
  - a `rev` conflict merges item by item;
  - `was` keeps earlier answers;
  - a round opens on a `build` or `reset` change, on Save round now and on Restart;
  - a changed item hash reopens the item;
  - numbering starts at 1 everywhere.
- **`serve.py`:**
  - every endpoint's success and error codes, as `test_serve` does today;
  - the inbox file is written atomically, under the right priority name;
  - `.listening` is read correctly for a live pid and a dead one.
- **`page.py wait`:**
  - it exits on a new file;
  - it exits at once when files are already waiting;
  - it lists blockers first;
  - the kqueue path and the fallback path both work (a flag forces the fallback in tests).
- **Smoke tests in headless Chrome:**
  - the parity list in section 11;
  - Send: the button state, the partial-send confirm and the delivery states;
  - Blocker: send now;
  - the thread view;
  - Restart from a checkpoint;
  - a live redraw that keeps my typing and the scroll position.
- **Converter:** golden tests on every `example/` page and on anonymised copies of each page type in use, with
  the HTML in and the expected JSON out.
- **Migration dry run:** convert a full copy of a site in a scratch folder, then compare every page's Copy results
  text, old against new. They must match.

## 14. Left to the builder

- **Names:** CLI flags, endpoint paths beyond the ones named here, and file names inside `_site/`.
- **The look** of the thread, the delivery states and Restart from. It follows `site.css` tokens. New UI pieces
  are designed with me before they're built.
- **The inline markup parser:** keep it tiny and escape-first.
- **Linux file watching:** inotify through ctypes, or the scandir fallback only. Either is fine; macOS is the
  target that matters.
- **Pruning `taken/`:** reuse the `_old/` pruner and its days setting, or give it its own.
- **The page-file size cap:** today's limit is 256 KB per save. Pick a cap that fits a long journey with many
  rounds (2 MB is a sane start) and refuse anything larger with a clear message.

## 15. Open point

If the spike shows that an idle agent isn't woken when its background command exits, I choose between operator
forwarding and an optional push channel before the build goes on.

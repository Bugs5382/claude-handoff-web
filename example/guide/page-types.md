# Page types

Every page an agent makes is one JSON file, `<folder>/<slug>.json`, in the `handoff.page/v1` format. The file
holds the page, every round of answers with who and when, and a reply thread per item. The site draws every page
from its file with one renderer, so a page never carries its own HTML, styles or scripts.

The format in full, the writer and the command line: [`PAGE-FILE.md`](../template/_site/PAGE-FILE.md). The HTTP
API and the inbox: [`PAGE-API.md`](../template/_site/PAGE-API.md). Working examples of most kinds are in
`example/demo/`.

## Before you start

- A running site (see [quick-start.md](quick-start.md)) and its folder for your pages, listed in `site.json`.
- Commands below run from the site folder. `page.py` lives in `_site/`.

## Publish a page

1. Write the definition: `schema`, `kind`, `title` and `items`, plus whatever the kind needs.
2. Create the page:

   ```bash
   python3 _site/page.py new app/design --from design.json
   ```

3. Give the owner the link: `http://<host>:<port>/app/design`. The page shows up on the folder and root
   indexes by itself; there is no `_status.json` entry to write and no index to rebuild.
4. Wait for answers in the background and act when the wait exits:

   ```bash
   python3 _site/page.py wait app
   ```

   It prints the submission files (blockers first). Move each one to `_inbox/app/taken/`, act on it, then
   answer on the page with `page.py reply`, and start the wait again.

To change a page, write the whole definition again with `page.py set app/design --from design.json`. Answers
are kept: an item whose content changed after a Yes comes back as "changed since round N", and a new `build`
or `reset` opens a new round. Never edit a page file by hand; every write goes through `page.py`, which holds
the lock.

## Kinds

A page's `kind` sets the default item type and what the page is for. Any item can set its own `type`, so one
page can mix them (see [Mixing item types](#mixing-item-types)).

| Kind | Default item | Answers | For |
|---|---|---|---|
| `review` | `section` | Yes / No / Changes | designs, plans, contracts, screens and re-reviews |
| `checklist` | `check` | Yes / No / Changes / Skipped | sign-off of delivered work; needs a `build` |
| `journey` | `step` | Yes / No / Changes / Skipped | ordered steps with checkpoints and Restart from |
| `backlog` | `choice` | the page's `options` | Start / Hold and the like; needs `options` |
| `questions` | `question` | free text | a page of open questions |
| `reference` | `info` | none | hand-off notes, email drafts, "what's built" |
| `status` | `info` | none | a live status page the agent rewrites as things move |

### review

Each item is a card with Yes / No / Changes; Changes needs a note. Items answered Yes in an earlier round are
hidden in the next one and stay in Copy results.

```json
{
  "schema": "handoff.page/v1",
  "kind": "review",
  "title": "Settings screen: design review",
  "summary": "Three sections to approve before the settings screen is built.",
  "status": {"state": "needs-you", "note": "Three sections of the settings screen design."},
  "items": [
    {"id": "s1", "title": "Purpose and behaviour",
     "body": [{"p": "A signed-in user changes their display name, notification e-mails and theme."}]},
    {"id": "s2", "title": "Layout",
     "body": [{"code": "[ Profile ]  [ Notifications ]  [ Theme ]"},
              {"image": "img/settings-tabs-top.svg", "alt": "Chosen: tabs across the top"}]},
    {"id": "s3", "title": "Errors and empty states",
     "body": [{"p": "A failed save keeps the typed value and shows **Couldn't save, retrying**."}]}
  ]
}
```

### checklist

One item per feature or fix, in test order. Each check can carry a `howto`, opened in its own pop-out window
with a Copy button on every code block. `dependsOn` keeps an item greyed and uncounted until the items it names
are Yes; `blockedBy` holds it until an agent replies with `--action unblock`.

```json
{
  "schema": "handoff.page/v1",
  "kind": "checklist",
  "title": "Example app 1.4.0: sign-off checklist",
  "build": "1.4.0-rc.2",
  "items": [
    {"id": "t1", "title": "Install", "body": [{"p": "The installer finishes and the service starts."}],
     "howto": [{"olist": ["Run the installer, then check the service is up."]},
               {"code": "./install.sh --prefix /opt/example-app"},
               {"code": "curl -s http://localhost:8080/healthz"}]},
    {"id": "t2", "title": "Sign in", "body": [{"p": "A new user can sign in and lands on the dashboard."}]},
    {"id": "t3", "title": "Export a report", "dependsOn": ["t2"],
     "body": [{"p": "Exporting the weekly report downloads a CSV with today's rows."}]}
  ]
}
```

### journey

Steps run in order: each step depends on the one before it unless it sets its own `dependsOn` (`[]` for none).
A Yes on a step with a `checkpoint` records that checkpoint. "Restart from" offers each checkpoint reached:
the steps up to it carry over as Yes, later steps start open, and the restart is sent to the page's route so
the agent can reset the environment.

```json
{
  "schema": "handoff.page/v1",
  "kind": "journey",
  "title": "Journey 1: first order",
  "build": "1.4.0-rc.2",
  "items": [
    {"id": "j1", "title": "Install and sign in as the first admin",
     "steps": ["Run the installer", "Sign in as the first admin"], "checkpoint": "after-install"},
    {"id": "j2", "title": "Add a product",
     "steps": ["Open Admin, Products", "Add a product called Demo laptop"], "checkpoint": "catalog-ready"},
    {"id": "j3", "title": "Order it as a user", "steps": ["Sign in as demo-user", "Order the Demo laptop"]}
  ]
}
```

### backlog

The page's `options` replace Yes / No / Changes. An item nobody picked counts as the default; the comment is
optional. Choices never block approval, and the card shows the counts ("1 start · 2 hold").

```json
{
  "schema": "handoff.page/v1",
  "kind": "backlog",
  "title": "Demo app backlog",
  "options": {"choices": [{"value": "start", "label": "Start"}, {"value": "hold", "label": "Hold"}], "default": "hold"},
  "items": [
    {"id": "b1", "title": "Export reports as PDF", "body": [{"p": "About two days."}]},
    {"id": "b2", "title": "Dark theme", "body": [{"p": "About one day."}]}
  ]
}
```

### questions

Open questions take free text and never block anything. `suggested` adds a "Use suggestion" button. Use a
question only when the answer isn't a choice.

```json
{
  "schema": "handoff.page/v1",
  "kind": "questions",
  "title": "Open questions for the release",
  "items": [
    {"id": "q1", "title": "How long should a changed e-mail stay unverified?", "suggested": "30 days",
     "body": [{"p": "The old e-mail stays active until the new one is verified."}]},
    {"id": "q2", "title": "Who signs off the release notes?"}
  ]
}
```

### reference

No answers and no bar: notes, drafts and "what's built". A `copy` block has its own Copy button.

```json
{
  "schema": "handoff.page/v1",
  "kind": "reference",
  "title": "Release 1.4.0 notes",
  "status": {"state": "reference", "note": "The notes and the email draft for 1.4.0."},
  "items": [
    {"id": "n1", "title": "What's in it", "body": [{"list": ["Settings screen with tabs", "CSV export"]}]},
    {"id": "n2", "title": "Email draft", "body": [{"copy": "Hi all,\n\n1.4.0 is out today.\n\nThanks,\nSam"}]}
  ]
}
```

### status

Like a reference page, but the agent rewrites it with `page.py set` as things move. Open tabs redraw in place.

```json
{
  "schema": "handoff.page/v1",
  "kind": "status",
  "title": "Migration status",
  "items": [
    {"id": "now", "title": "Now", "body": [{"p": "Copying the orders table: 62% done."}]},
    {"id": "next", "title": "Next", "body": [{"list": ["Switch reads to the new database", "Turn off the old one"]}]}
  ]
}
```

## Item types

| Type | Answers | Extra fields |
|---|---|---|
| `section` | Yes / No / Changes | `body` |
| `check` | adds Skipped | `body`, `howto`, `dependsOn`, `blockedBy` |
| `step` | adds Skipped | `steps`, `checkpoint`, `howto`, `dependsOn`, `blockedBy` |
| `screen` | Yes / No / Changes | `images` (`[{src, alt, caption}]`), `fields` (`[{name, type, rule}]`), `body` |
| `contract` | Yes / No / Changes | `fields`, `forms` (`[{name, fields}]`), `body` |
| `diff` | Yes / No / Changes | `old`, `new`, `code`: drawn as a word diff with a Diff / Final switch |
| `question` | free text | `body`, `suggested` |
| `choice` | the page's `options` | `body` |
| `info` | none | `body` |

Any answerable item can also set `answers` (its own set, such as `["yes", "no"]`), `skip: true` (adds Skipped
to that item), `dependsOn`, `blockedBy` and `section` (a group heading above it). The body blocks (`p`, `list`,
`olist`, `code`, `image`, `table`, `diff`, `copy`, `note`, `html`) are listed in `PAGE-FILE.md`.

### Mixing item types

One page can hold any mix. Each item answers its own way: here a section, a section with only Yes and No, a
question, a choice (which uses the page's `options`), a step and an info item.

```json
{
  "schema": "handoff.page/v1",
  "kind": "review",
  "title": "System defaults review",
  "options": {"choices": [{"value": "keep", "label": "Keep"}, {"value": "drop", "label": "Drop"}], "default": "keep"},
  "items": [
    {"id": "i1", "type": "info", "title": "Before you start", "body": [{"p": "Sign in as the first admin."}]},
    {"id": "d1", "title": "Every default asset type is there"},
    {"id": "d2", "title": "Default types can't be deleted", "answers": ["yes", "no"]},
    {"id": "d3", "type": "question", "title": "Which timezone should new sites use?", "suggested": "UTC"},
    {"id": "d4", "type": "choice", "title": "The sample data set"},
    {"id": "d5", "type": "step", "title": "Create a first asset", "steps": ["Open Assets", "Add a laptop"]}
  ]
}
```

### Screens, contracts and diffs

```json
{
  "schema": "handoff.page/v1",
  "kind": "review",
  "title": "Sign-up form",
  "items": [
    {"id": "f1", "type": "screen", "title": "The form",
     "images": [{"src": "img/settings-tabs-top.svg", "alt": "The form as built"}],
     "fields": [{"name": "email", "type": "text", "rule": "required, a valid address"}]},
    {"id": "f2", "type": "contract", "title": "The sign-up call",
     "fields": [{"name": "email", "type": "string", "rule": "required"}],
     "forms": [{"name": "Response", "fields": [{"name": "id", "type": "uuid", "rule": "always set"}]}]},
    {"id": "f3", "type": "diff", "title": "The welcome e-mail",
     "old": "Welcome! Your account is ready.", "new": "Welcome, Sam! Your account is ready to use."}
  ]
}
```

## Status and the index card

`status` is the page's index card: `state` (`needs-you`, `reference` or `done`), a one-line `note`, `chips`
and a `priority` (lower sorts first). Without a `state`, a page stays in Needs you until every counted item is
Yes, then shows as Done; reference and status pages show under Reference. Set it with:

```bash
python3 _site/page.py status app/design done --note "Shipped in 1.4.0"
```

## From today's page types

| Today's type | As a page file |
|---|---|
| Folder index card and manifest entry | the page's own `status`; no manifest |
| Design or review page | `review` |
| Unified review page | gone: each page is answered on its own page |
| Sign-off checklist | `checklist` |
| Decision page | a `review` whose items carry the options as content, or a `choice` item |
| Walk-through or ASCII mock | a `review` with `code` blocks |
| Hand-off note or email draft | a `reference` with a `copy` block |
| Live status page | `status` |
| Open question | a `question` item |
| Choices page (a backlog) | `backlog` |
| Diff item | a `diff` item or a `diff` block |

HTML pages keep working while a site moves over. `page.py convert <folder>/<page>.html` turns one into a page
file beside it, bringing its saved answers and round history along; see `PAGE-FILE.md`.

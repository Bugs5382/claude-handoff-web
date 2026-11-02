# Operating rules for this hand-off site

This folder is a running instance of claude-handoff-web: a review and sign-off site where agents publish
pages and the owner (`site.json` `owner`) answers them. Every agent or session that touches it follows
these rules. Full how-to: `_site/README.md`, `_site/PAGE-FILE.md` and `_site/PAGE-API.md`; page kinds with examples: the
template's `docs/page-types.md`.

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
- Every new page is a page file in your folder, `<folder>/<slug>.json`, created and changed only with
  `python3 _site/page.py` (`new`, `set`, `reply`, `status`). Never edit a page file by hand: `page.py` holds the
  lock. A page file needs no `_status.json` entry and no index rebuild.
- Give links as plain text (`http://<host>:<port>/<folder>/<slug>`). Never open a browser for the owner unless
  asked.

## Your inbox

- Send and "Blocker: send now" write to `_inbox/<agent>/` for the page's route (set by the operator). Keep
  `python3 _site/page.py wait <agent>` running in the background; when it exits, take each file it printed
  (blockers first) by moving it to `_inbox/<agent>/taken/`, act, answer on the page with `page.py reply`, and
  start the wait again.
- `python3 _site/page.py hook <agent>` prints one line when files are waiting or nothing is listening. Run it
  from a hook when you're next spoken to, so a lost wait is picked up again.

## Stale and _old/

- The owner's Stale button marks a page done; a page file moves to its folder's `_old/`, an HTML page is
  deleted. Don't recreate it unless asked.
- Before you replace a file, copy it to its folder's `_old/`. Files in `_old/` are pruned after 7 days.

## Choosing a page

Full walk-through with a network migration: `_site/GUIDE.md`. Pick the `kind` by what the person has to do:

- `review`: approve a design, plan or text. `checklist`: sign off delivered work on a `build`. `journey`: steps run in order, with checkpoints.
- `backlog`: pick from a list. `questions`: open questions. `reference` and `status`: reading only.
- `round`: a set of items to answer and send, with Accept risk. Without `phases` it's round single, sent from the bar. With `phases` it's round phases: phases `A`, `B`, steps `A1`, `A2`, and a Send per phase.
- Item types mix on a page: `section`, `check`, `step`, `screen`, `contract`, `diff`, `question`, `choice`, `info`.
- A phase's or item's `dependsOn` can name a phase or a step. Use it to say what waits on what.
- `"drafts": true` adds Generate an email to each item's More. `"deck": true` adds Build a deck to the bar's More.
- Run `python3 _site/page.py check <page>` before you hand a page over.

## When something lands in your inbox

Each file in `_inbox/<agent>/` has a `kind`. Blockers first.

- `send`: the person answered and these items are locked. Act, then reply under each item with `page.py reply`. A reply under a No or Changes clears it, and the note stays in its history. Change the item with `page.py set` if the data changed.
- `blocker`: one item is stopping them. Deal with it now.
- `email`: write the email from `recipient`, `ask`, `tone` and `context`, which holds the step, what changed between rounds, and the comments. For `change`, start from version `basedOn`. Answer with `page.py email <page> <id> --from <agent> --request <n> --subject "..." "body"`. This doesn't answer or lock the item.
- `deck`: build it from `framing` and `items`, which are only the final Yes and Accept risk items. Save it beside the page and reply under `_page` with the link.
- `restart`: reset the environment to the checkpoint.

## Extending the site

Everything custom goes in `custom/`, which no update touches, with `htm` templates and no build. `_site/CUSTOM.md` lists the elements (`Page`, `Round`, `Phase`, `Item`, `ItemMore`, `Answer`, `Button`, `Chip`, `EmailDraft`, `Thread`, `History`, `Restart`, `Footer`, `JumpBar`, `OpenIds`, `Blocks`, `TourButton`) and what stays stable. Never edit `_site/`: an update replaces it. Custom buttons and links go in the More menus as slots, never on the bar.

## Reviews

- Each item answers its own way: Yes / No / Changes (Changes needs a note), Skipped on checks and steps, the
  page's own choices on a backlog, free text on an open question. One page can mix them.
- A Send locks the items it carried until your next `page.py set` or `reply`, so always answer on the page.
- An item answered Yes in an earlier round, or sent as Yes, stays as a collapsed, locked row and in Copy results. A sent
  No or Changes clears once you reply under the item or change it, so answer item by item; your note stays in its
  thread. A Yes comes back only when its
  content changes ("changed since round N") or you reopen it with `page.py reply ... --reopen "reason"`.
- `dependsOn` greys an item until the items it names are Yes; `blockedBy` holds it until you reply with
  `--action unblock`.
- Never ask twice: when a checklist already answered something a review asks, close the review item from that
  answer.
- A new `build` or `reset` in the definition opens a new round; past rounds stay in the file and show under
  History. Nothing is built or merged until every item is Yes.
- HTML pages not converted yet keep their old rules: a `_status.json` entry, `gen-index.py`, answers through
  `/_save/` (`_site/SAVE-API.md`). Convert them with `python3 _site/page.py convert <folder>/<page>.html`.

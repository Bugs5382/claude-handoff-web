# Operator guide

How to use this site: what a person presses, what comes back, and what Claude does at each point. `PAGE-FILE.md` has the file format, and `CUSTOM.md` covers extending the site.

## How it works

Claude writes a page with `page.py`. The person answers it in the browser, and presses Send. That drops a file in Claude's inbox. Claude acts, then answers on the page, and the page updates by itself.

Keep `page.py listen <agent>` running under a monitor so Claude notices each Send, or `page.py wait <agent>` in the background, started again each time it exits. To set up a page's route:

```bash
python3 _site/page.py route ops/migration --to app --mode send
```

Every page has a Take the tour button, which walks through its real controls.

## A worked example: a network migration

Northwind is moving its Harbor site to a new core. The `sample-round-phases` page is this example, and `page.py samples <folder>` loads it.

1. **Claude writes the plan.** It's a `round` with phases: A Prepare, B Cut over, C Validate, D Retire. Each phase has a goal and steps `A1`, `A2`, `B1`. Phase A blocks B and C, and step A2 blocks B3.

   ```bash
   python3 _site/page.py new ops/migration --from plan.json
   ```

2. **The person answers phase A.** They press Yes on A1, then Changes on A2, the access switch inventory, and type "sw-harbor-2 looks wrong, and Quay is missing a switch". B and C show Blocked by A, and B3 shows Blocked by A2. Those links go to what's holding them.

3. **The person presses Send phase A.** The items sent lock, and everything else stays open. A banner says where it stands, and the bar shows "sent 21:44", then "picked up 21:46".

4. **Claude picks it up.** `page.py wait` exits and prints the file. Claude moves the file to `_inbox/<agent>/taken/`, reads the answers and re-verifies the inventory against the live switches.

5. **Claude answers on the page.** It replies under the item and updates the data:

   ```bash
   python3 _site/page.py reply ops/migration A2 --from app --action fixed "Re-verified. sw-harbor-2 moved and sw-quay-2 was missing."
   python3 _site/page.py set ops/migration --from plan.json
   ```

   The Yes on A1 stays as a collapsed, locked row. The Changes on A2 clears, its note moves to the item's history with Claude's reply, and the item shows "Updated: answer again". A reply about the whole page clears nothing, so always reply under the item.

6. **The person tells the network team.** On A2 they press More, then Generate an email. They enter who it's to ("The network team"), what they need ("Check the updated list before Friday's freeze") and the tone. They don't retype the inventory.

7. **Claude writes the email.** The submission has kind `email`, and its `context` holds the step, what changed between rounds, and the comments. Claude writes it and sends it back:

   ```bash
   python3 _site/page.py email ops/migration A2 --from app --request 4 --subject "Access switch inventory changed" "Hi all, ..."
   ```

   The email appears in A2 as To, Subject and Body, each with a copy button. The item isn't answered or locked. The person presses Ask for changes, types "shorter", and a new version comes back. Earlier versions stay readable.

8. **A risk gets accepted.** A3 says rollback takes 25 minutes. The person presses Accept risk and says how it's presented. That note is required. Phase A closes once every step is Yes or Accept risk, and B and C unblock.

9. **Devices can't be reached.** On A4, three devices refused the login. The person generates an email to whoever can grant access, the same way.

10. **The person presses Build a deck.** It's in the bar's More menu. It asks what they're trying to build, such as "a presentation on the migration timeline and risks". Only the items whose final answer is Yes or Accept risk go. Claude builds the deck, saves it beside the page, and replies with the link:

    ```bash
    python3 _site/page.py reply ops/migration _page --from app "[The deck](/ops/migration-deck.pptx)"
    ```

## Page types

Pick the `kind` by what the person has to do.

| Kind | Use it for | What the person does | What Claude does then |
|---|---|---|---|
| `review` | a design, plan or text to approve | Yes, No or Changes on each section, then Send | fixes what came back, and replies under each item |
| `checklist` | signing off delivered work on a `build` | runs each How to test, answers, can Skip | files or fixes what failed, then opens a new `build` |
| `journey` | a run of steps, each after the last | answers each step, can Restart from a checkpoint | resets the environment on a restart |
| `backlog` | picking from a list | picks a choice on each item | starts what was picked |
| `questions` | open questions with no fixed answers | types answers | uses them, and replies |
| `reference` | something to read | nothing | keeps it up to date |
| `status` | where a job stands | nothing | keeps it up to date |
| `round` | a set of items to answer and send, with Accept risk | answers, then Send, or a Send per phase | acts on what was sent, and replies under each item |

A `round` has two templates. Without `phases` it's round single: one set of items, sent from the bar. With `phases` it's round phases, as in the example above.

## Item types

Any page can mix them with `type`.

| Type | The person sees | They answer |
|---|---|---|
| `section` | text | Yes, No or Changes |
| `check` | a test, with How to test | adds Skipped |
| `step` | numbered steps, with How to test | adds Skipped |
| `screen` | pictures and fields | Yes, No or Changes |
| `contract` | fields and forms | Yes, No or Changes |
| `diff` | a change, with Diff and Final | Yes, No or Changes |
| `question` | a question | free text |
| `choice` | the page's `options`, or its own question with labelled options | a pick, or Other with text, plus a note |
| `info` | text | nothing |

## What each control does

| Control | What happens | What Claude does |
|---|---|---|
| Send | sends the answers and locks what was sent | reads the inbox file, acts, and replies |
| Send phase | the same, for one phase | the same |
| Blocker | sends one item straight away, and locks nothing | deals with it first |
| Copy results | copies the answers as text | nothing: the person pastes it |
| Unlock to change an answer | takes that Send back | nothing |
| More on an item | pops up that item's actions | depends on the action |
| Generate an email | asks who it's to, what's needed and the tone | writes it, with `page.py email` |
| Build a deck | asks what's being built | builds it, and replies with the link |
| Save round now | closes the round into History | nothing |
| Take the tour | walks through the page | nothing |

## Making new things

- **A new page:** write a definition and run `page.py new`. Check it first with `page.py check`.
- **A new custom page, action or tour:** put it in `custom/`, which no update touches. See `CUSTOM.md`.
- **Try it safely:** `page.py samples <folder>` loads a sample of every page type. Running it again resets them.

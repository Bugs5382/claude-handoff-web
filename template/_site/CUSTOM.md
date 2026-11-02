# Custom pages

`custom/` is yours. The installer never changes what's in it, so it survives every update. Nothing here needs a build: a custom template is plain JavaScript using `htm`.

The site loads two files after its own, when they exist:

- `custom/custom.css`, after `site.css`, so anything in it wins.
- `custom/custom.js`, before the first page draws.

Page files can also live in `custom/pages/`, and show at `/custom/pages/<slug>`.

## A custom template

`custom.js` adds a template by name. A page uses it with `"template": "<name>"` in its definition. A page whose template isn't there draws the usual way.

```js
const { html, templates } = window.HandoffSite;
templates["draft-round"] = ({ data, item }) => html`
  <p>A line of my own.</p>
  ${data.page.items.map((it, i) => item(it, i + 1))}`;
```

A template gets `{ data, local, item, sendPhase, goTo }` and returns what goes in the page's main column. The header, bar and History stay the site's own.

- `data`: what `GET /_page/<folder>/<slug>` returns: `page`, `states`, `phases`, `route`, `listening`, `diffs`.
- `local`: this tab's answers by item id.
- `item(it, n)`: draws one item card, with its answers, thread and email draft.
- `sendPhase(id)`: sends one phase of a round.
- `goTo(id)`: scrolls to an item or a phase.

## Per-item actions

Each item has a More button that pops up its actions, such as Draft email. `custom.js` can add its own. An entry gets the item and the page, and returns `{ name, label, onSelect, disabled }`, or `null` to skip that item.

```js
window.HandoffSite.itemActions.push(it => ({
  name: "copy-title", label: "Copy this step's title",
  onSelect: () => navigator.clipboard.writeText(it.title),
}));
```

## Elements

`window.HandoffSite` holds `html` (htm bound to React) and these elements. Their inputs are in `web/src/elements/` in the repo.

| Element | What it is |
|---|---|
| `Page` | a whole page file |
| `Round` | a round, single or with phases |
| `Phase` | one phase, with its goal and Send |
| `Item` | one card |
| `ItemMore` | an item's More button and the actions it pops up |
| `Answer` | the segmented answer buttons |
| `Button` | a named button, such as `send-btn` or `copy` |
| `Chip` | a status pill |
| `EmailDraft` | an item's draft, with its versions |
| `Thread` | an item's history |
| `History` | closed rounds |
| `Restart` | a journey's restart |
| `Footer`, `JumpBar`, `OpenIds` | the bar and its jump controls |
| `Blocks` | a list of body blocks |

## What stays stable

These don't change within a major version:

- **Page fields:** everything in `PAGE-FILE.md`.
- **The send path:** `POST /_page/<folder>/<slug>/send` and the `handoff.submission/v1` files in `_inbox/<agent>/`.
- **Events on `document`:** `handoff:page` when a page draws or redraws, with `detail.data`, and `handoff:answer` when an answer changes, with `detail.id` and `detail.value`.
- **The names above** and the classes in `site.css` they draw.

Anything else may change in any release.

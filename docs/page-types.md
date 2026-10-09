# Page types

The pages an agent creates on the hand-off site, what each is for, and a skeleton that works as-is with the
shared `/_site/` assets. Replace `<folder>`, `<owner>` and the placeholder text. Every page you add also
gets an entry in `<folder>/_status.json`; then run `python3 gen-index.py`.

Common rules:

- `<body class="site">` turns on the shared look; `<header class="top"><div class="wrap">` and
  `<main class="wrap">` give the standard frame.
- Review pages load `/_site/review.js?v=12` just before `</body>`; it brings `live.js` itself. Other pages
  load `/_site/live.js?v=12` with `data-mode="page"`.
- Answers are saved on the server; Copy results is what the owner pastes back to you.
- A round is one pass of answers under one `data-build` value or `data-review-reset` version. Bump either
  one and the server archives the round it replaces on its own (see `_site/SAVE-API.md` "Round history");
  nothing else is needed. Past rounds show in a collapsed "History" block at the page's bottom, in the More
  menu, and at `/<folder>/history/`.

## (a) Folder index card and manifest entry

**When:** always. The folder index (`/<folder>/`) and the root "Needs you now" list are generated from
`_status.json`; you never write index HTML.

**Required:** one key per page (`page.html`, `dir/` or `dir/page.html`), a `state`, a one-line `note`.
Optional: `chips` (custom labels), `priority` (lower sorts first, default 50).

```json
{
  "review/": { "state": "needs-you", "note": "The one place to answer: every open item from this folder." },
  "design-review.html": { "state": "needs-you", "note": "Three layout choices for the settings screen.", "chips": ["Decision needed"] },
  "release-notes-draft.html": { "state": "reference", "note": "Draft notes for the next release." },
  "old-plan.html": { "state": "done", "note": "Replaced by the design review." }
}
```

```bash
python3 gen-index.py
```

The card shows the title (the page's `<title>`), the note, chips (New, Updated, To review, Approved,
Reopened, plus yours), the open item count for review pages, and a Stale button for needs-you pages.

## (b) Design or review page

**When:** the owner has to approve content section by section: a design, a plan, screens, a walk-through.

**Required:** one `<h2>` per item (each becomes Yes / No / Changes), content under it, review.js. A section
is instead an open question (see (i)) when the answer isn't a choice between options.
**Body attributes:** `data-review-approved`, `data-review-reopen`, `data-review-reset` (see `_site/README.md`).

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Settings screen: design review</title>
<meta name="description" content="Three sections to approve before the settings screen is built.">
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site" data-review-approved="" data-review-reopen="">
<header class="top"><div class="wrap">
<h1>Settings screen: design review</h1>
<p>Answer each section Yes, No or Changes, then More, Copy results, and paste it back.</p>
</div></header>
<main class="wrap">
<h2>Purpose and behaviour</h2>
<p>What the screen is for and what each control does.</p>
<h2>Layout</h2>
<pre>+-----------------------------+
| Profile | Security | Alerts  |
+-----------------------------+</pre>
<h2>Errors and empty states</h2>
<p>What the owner sees when a save fails or there is nothing to show.</p>
</main>
<script src="/_site/review.js?v=12"></script>
</body></html>
```

## (c) Unified review page

**When:** always, once a folder has more than one review page. It is the one place the owner answers.

**Required:** the source pages are `needs-you` in `_status.json`; build with the script. Never hand-edit
the output; set attributes on the source pages and rebuild.

```bash
python3 _site/build-review.py <folder>      # writes <folder>/review/index.html
```

```json
"review/": { "state": "needs-you", "note": "The one place to answer: every open item from this folder." }
```

Each source page becomes a collapsed group (one open at a time): title, summary, open count, chips,
"Full page" and Stale. Item ids are prefixed with the page (`design-review.s2`), and the source page's
approved, reopened and reset attributes carry through.

## (d) Sign-off checklist

**When:** delivered work (features, fixes, a release) needs the owner to test it on the real thing.

**Required:**

- items in logical test order (install, setup, sign-in, features, update, revert), never by issue number;
- each item a `<section data-review-question="id" data-title="...">` with what to check;
- test steps in a `<template data-howto>` (they open in a pop-out with Copy buttons on every `<pre>`);
- `data-build` (the build under test), `data-review-skip="on"` (adds Skipped, locked),
  `data-review-h2="off"` (only the sections are items);
- dependencies in `data-review-blocked="id=what blocks it|..."`: greyed, not counted until fixed.

When every open item is answered the bottom bar turns green; all Yes shows APPROVED.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Example app 1.4.0: sign-off checklist</title>
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site" data-review-h2="off" data-review-skip="on" data-build="1.4.0-rc.2"
      data-review-blocked="t3=t2 (sign-in must pass first)">
<header class="top"><div class="wrap">
<h1>Example app 1.4.0: sign-off checklist</h1>
<p>Build 1.4.0-rc.2. Test in order; mark Yes, No, Changes or Skipped.</p>
</div></header>
<main class="wrap">
<section data-review-question="t1" data-title="Install">
  <h2>1. Install</h2>
  <p>The installer finishes and the service starts.</p>
  <template data-howto>
    <ol><li>Run the installer:</li></ol>
    <pre>./install.sh --prefix /opt/example-app</pre>
    <ol start="2"><li>Check the service is up:</li></ol>
    <pre>curl -s http://localhost:8080/healthz</pre>
  </template>
</section>
<section data-review-question="t2" data-title="Sign in">
  <h2>2. Sign in</h2>
  <p>A new user can sign in and lands on the dashboard.</p>
  <template data-howto><p>Open the app, sign in as <code>demo-user</code>, check the dashboard loads.</p></template>
</section>
<section data-review-question="t3" data-title="Export a report">
  <h2>3. Export a report</h2>
  <p>Exporting the weekly report downloads a CSV with today's rows.</p>
</section>
</main>
<script src="/_site/review.js?v=12"></script>
</body></html>
```

## (e) Decision page

**When:** a choice needs context a chat question can't carry (screens, trade-offs, a table), but only a few
options. One section per decision.

**Required:** the options, the recommended one marked, and what Yes / No / Changes mean, stated in the
section.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Decision: where exports are stored</title>
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site">
<header class="top"><div class="wrap"><h1>Decision: where exports are stored</h1>
<p>One decision. Yes takes the recommended option.</p></div></header>
<main class="wrap">
<h2>Storage for exported reports</h2>
<table>
  <tr><th>Option</th><th>Good</th><th>Costs</th></tr>
  <tr><td><b>A. Object storage (Recommended)</b></td><td>Cheap, scales</td><td>One more credential</td></tr>
  <tr><td>B. Database table</td><td>No new service</td><td>Grows the database</td></tr>
  <tr><td>C. Local disk</td><td>Simplest</td><td>Lost on redeploy</td></tr>
</table>
<p class="muted">Yes = A. No = none of these (say why). Changes = B or C (say which).</p>
</main>
<script src="/_site/review.js?v=12"></script>
</body></html>
```

## (f) Walk-through or ASCII mock

**When:** showing a flow or a screen before it exists: one step or screen per section.

**Required:** one `<h2>` per step, the mock in a `<pre>`, one line on what happens next.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>First-run setup: walk-through</title>
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site">
<header class="top"><div class="wrap"><h1>First-run setup: walk-through</h1>
<p>Four screens. Approve each one.</p></div></header>
<main class="wrap">
<h2>1. Welcome</h2>
<pre>+----------------------------------+
|  Welcome to Example App          |
|  [ Start setup ]                 |
+----------------------------------+</pre>
<p>Start setup goes to the admin account screen.</p>
<h2>2. Admin account</h2>
<pre>+----------------------------------+
|  Admin name  [______________]    |
|  Password    [______________]    |
|  [ Back ]            [ Next ]    |
+----------------------------------+</pre>
<p>Next checks the password rules, then goes to the network screen.</p>
</main>
<script src="/_site/review.js?v=12"></script>
</body></html>
```

## (g) Handoff note or email draft

**When:** text the owner sends on to someone else. Reference, not a review: state `reference` in
`_status.json`, or add one `<h2>` and review.js if the wording needs approval.

**Required:** the text in one block with a Copy button.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Email draft: maintenance window</title>
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site">
<header class="top"><div class="wrap"><h1>Email draft: maintenance window</h1>
<p>To: the operations list. Press Copy, paste into your mail client.</p></div></header>
<main class="wrap">
<p><button type="button" id="copy">Copy</button></p>
<pre id="text">Subject: Maintenance window on Saturday

Hello team,

Example App will be offline on Saturday from 06:00 to 07:00 for an upgrade.
Nothing is needed from you.

Thanks</pre>
</main>
<script>
document.getElementById("copy").addEventListener("click", async e => {
  await navigator.clipboard.writeText(document.getElementById("text").textContent);
  e.target.textContent = "Copied";
});
</script>
<script src="/_site/live.js?v=12" data-mode="page"></script>
</body></html>
```

## (h) Live status page

**When:** something runs for a while (a rollout, a migration, a long test) and the owner wants to watch it.
Reference: state `reference` while it runs, `done` when it ends.

**Required:** live.js in page mode. Rewrite the file as things change; the page reloads itself (never while
the owner is typing) and keeps the scroll position.

```html
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rollout status: example app 1.4.0</title>
<link rel="stylesheet" href="/_site/site.css?v=12">
</head>
<body class="site">
<header class="top"><div class="wrap"><h1>Rollout status: example app 1.4.0</h1>
<p>Updated 10:42. This page refreshes itself.</p></div></header>
<main class="wrap">
<table>
  <tr><th>Step</th><th>State</th><th>When</th></tr>
  <tr><td>Build</td><td><span class="chip c-done">Done</span></td><td>10:05</td></tr>
  <tr><td>Deploy to test</td><td><span class="chip c-done">Done</span></td><td>10:20</td></tr>
  <tr><td>Smoke tests</td><td><span class="chip c-review">Running</span></td><td>10:40</td></tr>
  <tr><td>Deploy to production</td><td><span class="chip">Waiting</span></td><td></td></tr>
</table>
</main>
<script src="/_site/live.js?v=12" data-mode="page"></script>
</body></html>
```

## (i) Open question

**When:** something an item on a review or design page needs from the owner isn't a choice between
options: a free-text answer. Use one only for that; a choice with options is still Yes / No / Changes or
an `AskUserQuestion`-style decision, never this.

**Required:** `data-review-type="question"` on the `<h2>` (or the `[data-review-question]` element on a
converted page), the question as its title, context in the content under it. Optional: `data-suggested`
with a suggested answer; review.js adds a "Use suggestion" button that fills it in.

**Not a blocker:** a question has no Blocker button, is never counted in the open-items count and never
holds up the page's approval. It gets its own small count ("n questions unanswered") and, in Copy
results, its own `Q <id>: <answer>` line in a block at the end, after the approval line.

```html
<h2 data-review-type="question" data-suggested="Nightly, 02:00 US/Eastern">When should the sync job run?</h2>
<p>Pick a schedule that doesn't land in the middle of the backup window.</p>
```

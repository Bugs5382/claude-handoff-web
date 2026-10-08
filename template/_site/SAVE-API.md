# Save API: keeping answers on the server

Answers on review pages and checklists are stored on the server that serves the site, never only in the
browser. `_site/review.js` already does this. A page with its own answer script (a checklist that sets
`<body data-review-controls="off">`) follows this spec to do the same.

## Endpoints

| Method | Path | Body | Result |
|---|---|---|---|
| `GET` | `/_save/<name>.json` | none | `200` with the JSON last stored (plus `Last-Modified`), or `404` if nothing is stored yet |
| `PUT` | `/_save/<name>.json` | JSON, at most 256 KB, `Content-Type: application/json` | `204`; the file is replaced atomically |

- `<name>` is `[a-z0-9._-]{1,120}`, not starting with a dot. Anything else: `405`.
- Bad JSON: `400`. Missing or wrong `Content-Type`: `415`. Over 256 KB: `413`.
- The whole document is replaced on each `PUT` (last writer wins). Send the full state every time.
- `stale-log` and `prune-log` are reserved names (read-only).
- Responses carry `Cache-Control: no-store`. The `_saved/` folder itself is never served.

## Page key

Use the page's existing localStorage key so answers carry over, sanitised to the name rule:

```js
function pageKey(k) {
  let s = k.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[-.]+|-+$/g, "");
  if (s.length > 120) { let h = 0; for (const c of k) h = (h * 31 + c.charCodeAt(0)) >>> 0; s = s.slice(0, 111) + "-" + h.toString(36); }
  return s || "page";
}
const SAVE_URL = "/_save/" + pageKey(KEY) + ".json";   // KEY = the page's old localStorage key
```

## What a page must do

1. **Load first, render second.** `GET SAVE_URL` before drawing answers.
   - `200`: use it.
   - `404`: start empty.
   - Network error or `5xx`: start from memory (and any local copy), show "Not saved, retrying", and keep
     retrying the `GET`. Don't `PUT` until a `GET` has worked, then merge: the server copy, with every item
     this tab changed laid over it.
2. **Migrate once.** If localStorage still holds `KEY`, fill in what the server copy lacks from it (items the
   server doesn't have, or has with no answer), `PUT` the result, `GET` it back, and only when the read-back
   equals what was sent, `localStorage.removeItem(KEY)`. If any step fails, keep the local copy and try again
   after the next good save.
3. **Save on every change,** debounced 500 ms: `PUT` the whole state. On success show `Saved hh:mm`. On failure
   show `Not saved, retrying` and retry with backoff (1 s, 2 s, 4 s, up to 15 s). Never drop the in-memory
   answers.
4. **Never lose an answer on reload.** While a save is pending: don't soft-reload (live.js checks
   `window.siteReview.unsaved()` when it exists; expose the same function), and in `beforeunload` send one
   `fetch(SAVE_URL, {method: "PUT", keepalive: true, ...})` and ask the browser to confirm leaving.
5. **Stop writing localStorage** for answers. Keep the state shape and the Copy results format unchanged.

## Minimal client

```js
async function getBox() {
  const r = await fetch(SAVE_URL, { cache: "no-store" });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error("GET " + r.status);
  return r.json();
}
async function putBox(obj) {
  const r = await fetch(SAVE_URL, { method: "PUT", headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify(obj), cache: "no-store" });
  if (r.status !== 204) throw new Error("PUT " + r.status);
}
let seq = 0, sent = 0, timer = null, fails = 0;
function persist() { seq++; clearTimeout(timer); timer = setTimeout(flush, 500); }
async function flush() {
  const s = seq;
  try { await putBox(state); sent = s; fails = 0; status("Saved " + new Date().toTimeString().slice(0, 5)); }
  catch (e) { fails++; status("Not saved, retrying", true); timer = setTimeout(flush, Math.min(15000, 1000 * 2 ** fails)); return; }
  if (sent !== seq) timer = setTimeout(flush, 500);
}
window.siteReview = Object.assign(window.siteReview || {}, { unsaved: () => sent !== seq });
```

## Checking it

- Answer an item, reload with localStorage cleared: the answer is still there.
- `curl -s http://<host>:<port>/_save/<name>.json` shows the stored state.
- Block `/_save/` (devtools request blocking): the status turns to "Not saved, retrying"; unblock it and it
  saves by itself.

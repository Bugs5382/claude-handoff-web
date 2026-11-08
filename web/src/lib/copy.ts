// Click handling for the small inline Copy buttons that inline(text, {copy: true}) writes into the page.

/** Copy text: the clipboard API where the browser allows it, else a hidden textarea, else select the source text. */
export async function copyText(text: string, src?: Element | null): Promise<"copied" | "selected" | "failed"> {
  try {
    if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return "copied"; }
  } catch { /* fall through to the older route */ }
  const ta = document.createElement("textarea");
  ta.value = text; ta.readOnly = true; ta.style.cssText = "position:fixed;top:0;left:0;opacity:0";
  document.body.appendChild(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand("copy"); } catch { ok = false; }
  ta.remove();
  if (ok) return "copied";
  if (src) { const r = document.createRange(); r.selectNodeContents(src); const sel = window.getSelection(); sel?.removeAllRanges(); sel?.addRange(r); return "selected"; }
  return "failed";
}

const timers = new WeakMap<Element, number>();

/** One delegated click handler for every .copy-inline button on the page. */
export async function copyInline(e: Event): Promise<void> {
  const b = (e.target as Element | null)?.closest?.("button.copy-inline") as HTMLButtonElement | null;
  if (!b) return;
  const done = await copyText(b.dataset.copy ?? "", b.previousElementSibling);
  b.dataset.state = done; b.title = done === "copied" ? "Copied" : done === "selected" ? "Selected, press Ctrl+C" : "";
  const t = timers.get(b); if (t) clearTimeout(t);
  timers.set(b, window.setTimeout(() => { delete b.dataset.state; b.removeAttribute("title"); }, 1500));
}

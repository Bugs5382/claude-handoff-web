import type { PageData } from "@/lib/types";

/** A small moment on the page: the element to mark and which moment it gets. */
export interface Moment { selector: string; name: string }

const card = (id: string) => `[data-review-question="${CSS.escape(id)}"]`;

/** What just happened between two versions of a page. The first draw has no moments. */
export function momentsFor(prev: PageData | null, next: PageData): Moment[] {
  if (!prev) return [];
  const out: Moment[] = [];
  const add = (selector: string, name: string) => out.push({ selector, name });
  const p = prev.page, n = next.page;
  if (n.submissions.length > p.submissions.length) {
    const sent = n.submissions.slice(p.submissions.length).filter(s => s.kind === "send");
    if (sent.length) add(".rvbar", "send");
    for (const s of sent) for (const id of s.items) add(card(id), "send");
  }
  for (const [id, st] of Object.entries(next.states)) {
    if (st.hidden && !prev.states[id]?.hidden) add(card(id), st.answer === "risk" ? "risk" : "settle");
    const before = p.thread[id]?.length ?? 0, now = n.thread[id]?.length ?? 0;
    if (now > before) add(`${card(id)} .thread .te:last-child`, "reply");
    const had = p.emails?.[id]?.length ?? 0, has = n.emails?.[id]?.length ?? 0;
    if (has > had) add(`[data-email="${CSS.escape(id)}"]`, "draft");
  }
  if ((n.thread._page?.length ?? 0) > (p.thread._page?.length ?? 0)) { add("#replies .thread .te:last-child", "reply"); add(".rvbar .dlv", "reply"); }
  for (const [id, ph] of Object.entries(next.phases)) if (ph.closed && !prev.phases[id]?.closed) add("#phase-" + CSS.escape(id), "phase");
  return out;
}

const QUIET = 900;

function typing(): boolean {
  const a = document.activeElement;
  return !!a && (a.tagName === "TEXTAREA" || a.tagName === "INPUT" || (a as HTMLElement).isContentEditable);
}

/** Plays moments. They only change colour, never layout, and nothing plays while someone types or asks for less motion. */
export function play(moments: Moment[]): void {
  if (typing() || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  for (const m of moments) {
    document.querySelectorAll<HTMLElement>(m.selector).forEach(el => {
      el.dataset.moment = m.name;
      setTimeout(() => { if (el.dataset.moment === m.name) delete el.dataset.moment; }, QUIET);
    });
  }
}

import type { ItemDef, Local, Locals, PageData, PageDoc, Round, Submission } from "@/lib/types";

// What render.js and review.js work out from a page file, one function each.
const TYPE_BY_KIND: Record<string, string> = { review: "section", checklist: "check", journey: "step", backlog: "choice", questions: "question", reference: "info", status: "info", round: "section" };
export const typeOf = (p: PageDoc, it: ItemDef): string => it.type ?? TYPE_BY_KIND[p.kind];
export const openRound = (p: PageDoc): Round => p.rounds[p.rounds.length - 1];

const IN: Record<string, string> = { yes: "yes", no: "no", changes: "chg", skipped: "skip", risk: "risk" };
const OUT: Record<string, string> = { yes: "yes", no: "no", chg: "changes", skip: "skipped", risk: "risk" };
export const DONE = ["yes", "risk"];
export const answerIn = (a: string): string => IN[a] ?? a;

export const phaseOf = (id: string): string => /^[A-Z]+/.exec(id)?.[0] ?? "";

export function toLocal(data: PageData): Locals {
  const p = data.page, r = openRound(p), out: Locals = {};
  const byId = new Map(p.items.map(it => [it.id, it]));
  for (const [id, a] of Object.entries(r.answers)) {
    const it = byId.get(id); if (!it) continue;
    const t = typeOf(p, it);
    if (t === "question") out[id] = { a: a.answer ?? "" };
    else if (t === "choice") out[id] = { v: a.answer ?? "", n: a.note ?? "" };
    else if (DONE.includes(a.answer) && data.states[id]?.reopened) out[id] = { v: "", n: a.note ?? "" };
    else { out[id] = { v: IN[a.answer] ?? "", n: a.note ?? "" }; if (a.answer === "skipped") out[id].locked = true; }
  }
  for (const [id, s] of Object.entries(data.states)) if (s.hidden) out[id] = { v: s.answer === "risk" ? "risk" : "yes", n: out[id]?.n ?? "" };
  for (const s of p.submissions) {
    if (s.kind !== "blocker" || s.round !== r.round) continue;
    for (const id of s.items) out[id] = { v: "", n: "", ...out[id], blocker: true };
  }
  return out;
}

export function toAnswer(p: PageDoc, id: string, s: Local | undefined): { answer: string; note: string } {
  const it = p.items.find(x => x.id === id) as ItemDef, t = typeOf(p, it);
  if (t === "question") return { answer: s?.a ?? "", note: "" };
  if (t === "choice") return { answer: s?.v ?? "", note: s?.n ?? "" };
  return { answer: OUT[s?.v ?? ""] ?? "", note: s?.n ?? "" };
}

export function blockers(data: PageData): Record<string, string> {
  const out: Record<string, string> = {};
  let prev: string | null = null;
  for (const it of data.page.items) {
    const t = typeOf(data.page, it);
    if (t === "info") continue;
    const deps = it.dependsOn ?? (t === "step" && prev ? [prev] : []);
    if (t === "step") prev = it.id;
    if (it.blockedBy && !(data.page.thread[it.id] ?? []).some(r => r.action === "unblock")) out[it.id] = it.blockedBy;
    else {
      const met = (x: string) => (data.phases[x] ? data.phases[x].closed : DONE.includes(data.states[x]?.answer ?? ""));
      const held = data.page.phases ? data.phases[phaseOf(it.id)]?.blocked : null;
      const d = deps.find(x => !met(x)) ?? held;
      if (d) out[it.id] = d;
    }
  }
  return out;
}

export function heldIds(p: PageDoc): string[] {
  const r = openRound(p), nums = r.held ?? (r.awaiting ? [r.awaiting] : []);
  return [...new Set(nums.flatMap(n => p.submissions[n - 1].items ?? []))];
}
export const heldBy = (p: PageDoc): Submission | null => { const n = openRound(p).awaiting; return n ? p.submissions[n - 1] : null; };

export interface CountItem { id: string; kind: "ync" | "choice" | "question" }

/** What the bottom bar counts: the rules of rvCount in review.js. */
export function count(items: CountItem[], s: Locals, hidden: Set<string>, blocked: Record<string, string>) {
  const S = (id: string): Local => s[id] ?? {};
  const ync = items.filter(it => it.kind === "ync"), choice = items.filter(it => it.kind === "choice");
  const counted = ync.filter(it => !hidden.has(it.id) && !S(it.id).locked && !blocked[it.id]);
  const unanswered = (it: CountItem) => !S(it.id).v || ((S(it.id).v === "chg" || S(it.id).v === "risk") && !(S(it.id).n ?? "").trim());
  const cCounted = choice.filter(it => !blocked[it.id]);
  const open = counted.filter(unanswered), cOpen = cCounted.filter(it => !S(it.id).v);
  const total = counted.length + cCounted.length, answered = total - open.length - cOpen.length;
  const hiddenN = ync.filter(it => hidden.has(it.id)).length;
  const blockedN = ync.concat(choice).filter(it => !hidden.has(it.id) && blocked[it.id]).length;
  const yesAll = counted.every(it => DONE.includes(S(it.id).v ?? ""));
  const allHidden = total === 0 && hiddenN > 0 && !blockedN;
  const allDone = (total > 0 && answered === total) || allHidden;
  return {
    total, answered, allDone, approved: allDone && (counted.length > 0 || allHidden) && yesAll,
    yncTotal: counted.length, choiceTotal: cCounted.length,
    openIds: items.filter(it => open.includes(it) || cOpen.includes(it)).map(it => it.id),
    hidden: hiddenN, blocked: blockedN,
    skipped: ync.filter(it => !hidden.has(it.id) && S(it.id).locked).length,
    blockers: ync.filter(it => !hidden.has(it.id) && S(it.id).blocker).length,
    qOpen: items.filter(it => it.kind === "question" && !(S(it.id).a ?? "").trim()).length,
    choiceOnly: choice.length > 0 && ync.length === 0,
  };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const clock = (iso?: string): string => String(iso ?? "").slice(11, 16);
export const stamp = (iso?: string): string => { const m = /^\d{4}-(\d\d)-(\d\d)T(\d\d:\d\d)/.exec(iso ?? ""); return m ? `${MONTHS[+m[1] - 1]} ${+m[2]}, ${m[3]}` : ""; };

export interface Delivery { kind: string; to: string; state: string; text: string; bar?: string; full?: string }

export const cpName = (cp: string): string => { const t = cp.replace(/[-_]+/g, " ").trim(); return t.charAt(0).toUpperCase() + t.slice(1); };

/** Where a Send, Blocker or Restart stands. */
export function deliveryOf(data: PageData, s: Submission): Delivery {
  const to = s.to ?? data.route.to;
  const replies = Object.values(data.page.thread ?? {}).flat().filter(x => x.at > s.at).sort((a, b) => a.at.localeCompare(b.at));
  const reply = replies[replies.length - 1];
  const restart = data.page.rounds.find(r => r.round === s.round)?.restart ?? "";
  const label = s.kind === "restart" ? "Restarted from " + cpName(restart) : s.kind === "blocker" ? "Blocker sent" : "Sent";
  const base = { kind: s.kind, to };
  if (reply) {
    const t = reply.text.length > 90 ? reply.text.slice(0, 89) + "\u2026" : reply.text;
    return { ...base, state: "replied", text: `${reply.from} replied ${clock(reply.at)}: ${t}`, bar: `${reply.from} replied ${clock(reply.at)}`, full: reply.text };
  }
  if (s.state === "failed") return { ...base, state: "failed", text: `${label} failed ${clock(s.at)} · it didn't reach ${to}.` };
  if (s.state === "taken") return { ...base, state: "taken", text: (s.kind === "restart" ? `${label} ${clock(s.at)} · picked up by ` : "Picked up by ") + `${to} ${clock(s.takenAt)}` };
  const deaf = to === data.route.to && !data.listening;
  return { ...base, state: deaf ? "deaf" : "sent", text: `${label} ${clock(s.at)}` + (deaf ? ` · ${to} isn't listening.` : "") };
}

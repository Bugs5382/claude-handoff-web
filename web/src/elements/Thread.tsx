import { useState } from "react";
import { flushSync } from "react-dom";
import { stamp } from "@/lib/model";
import { inline } from "@/lib/text";
import type { PageData, Reply } from "@/lib/types";

const ANS_LABEL: Record<string, string> = { yes: "Yes", no: "No", changes: "Changes", skipped: "Skipped" };
const ANS_CLASS: Record<string, string> = { yes: "a-yes", no: "a-no", changes: "a-chg", skipped: "skp" };
const ACTION_LABEL: Record<string, string> = { filed: "Filed", fixed: "Fixed", reopen: "Reopened", unblock: "Unblocked", wontfix: "Won't fix" };
const SHOWN = 4;

export interface Entry { kind: string; at: string; who: string; round?: number; action: string; tag: string; tagClass: string; html: string; raw?: string; reason?: string; ref?: string }

export const replyEntry = (x: Reply): Entry => ({
  kind: "reply", at: x.at, who: x.from, action: x.action ?? "info", tag: ACTION_LABEL[x.action ?? ""] ?? "", tagClass: "t-" + (x.action ?? "info"),
  html: inline(x.text), raw: x.text, reason: x.action === "reopen" ? x.reason : "", ref: x.ref,
});

/** An item's answers from past rounds, what the agent handled, and the replies. */
export function itemEntries(data: PageData, id: string): Entry[] {
  const out: Entry[] = [];
  const answer = (a: { answer: string; note?: string; at?: string }, round: number): Entry => ({
    kind: "answer", at: a.at ?? "", who: "You", round, action: a.answer, tag: ANS_LABEL[a.answer] ?? a.answer, tagClass: ANS_CLASS[a.answer] ?? "a-other", html: inline(a.note).replace(/<[^>]+>/g, "") });
  for (const r of data.page.rounds.slice(0, -1)) { const a = r.answers[id]; if (a && (a.answer || a.note)) out.push(answer(a, r.round)); }
  for (const r of data.page.rounds) for (const h of r.handled?.[id] ?? []) {
    out.push(answer(h, r.round));
    if (h.via === "definition") out.push({ kind: "reply", at: h.handled, who: data.route.to, action: "info", tag: "", tagClass: "t-info", html: "Changed this item." });
  }
  for (const x of data.page.thread[id] ?? []) out.push(replyEntry(x));
  return out;
}

export interface ThreadProps { entries: Entry[]; label: string }

export function Thread({ entries, label }: ThreadProps) {
  const [all, setAll] = useState(false);
  if (!entries.length) return null;
  const list = [...entries].sort((a, b) => a.at.localeCompare(b.at));
  const fold = !all && list.length > SHOWN ? list.length - SHOWN : 0;
  return (
    <ol className="thread" aria-label={label}>
      {fold > 0 && <li className="te-more"><button type="button" onClick={() => flushSync(() => setAll(true))}>Show {fold} earlier</button></li>}
      {list.map((e, i) => (
        <li key={i} className="te" data-kind={e.kind} data-action={e.action} hidden={i < fold}>
          <span className="te-mark" aria-hidden="true" />
          <div className="te-body">
            <p className="te-head"><span className="te-who">{e.who}</span>{e.round ? <span className="te-round">Round {e.round}</span> : null}
              {e.tag ? <span className={"te-tag " + e.tagClass}>{e.tag}</span> : null}<time dateTime={e.at}>{stamp(e.at)}</time></p>
            {(e.html || e.reason || e.ref) && <p className="te-line">{e.html && <span className="te-text" dangerouslySetInnerHTML={{ __html: e.html }} />}
              {e.reason && e.reason !== e.raw ? <span className="te-reason">{e.reason}</span> : null}{e.ref ? <span className="te-ref">{e.ref}</span> : null}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}

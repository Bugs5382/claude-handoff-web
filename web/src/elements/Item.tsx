import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Answer, type AnswerOption } from "@/elements/Answer";
import { Blocks, ItemExtras } from "@/elements/Blocks";
import { Chip } from "@/elements/Chip";
import { Thread, type Entry } from "@/elements/Thread";
import { openHowto } from "@/lib/howto";
import type { ItemDef, ItemState, Local } from "@/lib/types";

const LABEL: Record<string, string> = { yes: "Yes", no: "No", chg: "Changes", skip: "Skipped" };
const PILL: Record<string, string> = { yes: "Yes", no: "No", chg: "Changes", skip: "Skipped (locked)" };
const TONE: Record<string, string> = { yes: "a-yes", no: "a-no", chg: "a-chg", skip: "skp" };
const ANS: Record<string, string> = { yes: "yes", no: "no", changes: "chg", skipped: "skip" };
const BASE: Record<string, string[]> = { check: ["yes", "no", "chg", "skip"], step: ["yes", "no", "chg", "skip"] };

export function optionsFor(it: ItemDef, type: string): AnswerOption[] {
  let set = it.answers ? it.answers.map(a => ANS[a] ?? a) : (BASE[type] ?? ["yes", "no", "chg"]);
  if (it.skip && !set.includes("skip")) set = [...set, "skip"];
  return set.map(value => ({ value, label: LABEL[value] }));
}

export interface ItemProps {
  item: ItemDef;
  n: number;
  type: string;
  state?: ItemState;
  value: Local;
  /** Who or what is holding it, for Blocked by. */
  blockedBy?: string;
  /** Sent, and waiting on the agent. */
  held?: boolean;
  /** A sent No or Changes the agent dealt with. */
  handled?: boolean;
  entries: Entry[];
  diffs?: Record<string, string>;
  build?: string | null;
  choices?: { value: string; label: string }[];
  defaultChoice?: string;
  blockerLabel: string;
  blockerTitle: string;
  isItem: (id: string) => boolean;
  goTo: (id: string) => void;
  onChange: (next: Local) => void;
  onBlocker: (note: string) => void;
}

/** One numbered card: id, status, content, its history, answers and the note box. */
export function Item(p: ItemProps) {
  const { item: it, n, type, state, value, blockedBy, held, handled } = p;
  const [noteOpen, setNoteOpen] = useState(false);
  const [shown, setShown] = useState(false);
  const how = useRef<HTMLDivElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const qa = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { if (qa.current) { qa.current.style.height = "auto"; qa.current.style.height = qa.current.scrollHeight + 2 + "px"; } });
  const group = it.section ? <h2 className="group-h">{it.section}</h2> : null;
  const content = <>
    <ItemExtras item={it} diffs={p.diffs} isDiff={type === "diff"} />
    <Blocks blocks={it.body} id={it.id} diffs={p.diffs} />
    {it.howto && <div hidden ref={how}><Blocks blocks={it.howto} id={it.id} part="howto" diffs={p.diffs} /></div>}
    <Thread entries={p.entries} label={"History of " + it.id} />
  </>;
  if (type === "info") return <>{group}<section className="info" data-item={it.id}><h2>{n}. {it.title}</h2>{content}</section></>;

  const settled = !!state?.hidden;
  const locked = !!value.locked || !!blockedBy || !!held || settled;
  const v = value.v ?? "", note = value.n ?? "";
  const blocked = blockedBy ? <span className="st blk">Blocked by {p.isItem(blockedBy)
    ? <a className="rid" href={"#rv-" + encodeURIComponent(blockedBy)} title={"Go to " + blockedBy} onClick={e => { e.preventDefault(); p.goTo(blockedBy); }}>{blockedBy}</a> : blockedBy}</span> : null;
  const rid = <a className="rid" href={"#rv-" + encodeURIComponent(it.id)} title={"Go to " + it.id} onClick={e => { e.preventDefault(); flushSync(() => setShown(true)); p.goTo(it.id); }}>{it.id}</a>;
  const howBtn = it.howto && <button type="button" className="howto-btn" onClick={e => { e.preventDefault(); if (how.current) openHowto(how.current, it.id, it.title, p.build); }}>How to test {"↗"}</button>;

  if (type === "question") return <>{group}
    <section data-item={it.id} data-review-question={it.id} data-title={it.title} data-review-type="question" className={"rvcard" + (blockedBy ? " is-blocked" : "")}>
      <div className="rvhead">{rid}<span className="sp" /><span className="st2" />{blocked ?? (state?.reopened ? <Chip tone="reo">Reopened: {state.reopened}</Chip> : <Chip>Question</Chip>)}</div>
      <h2>{n}. {it.title}</h2>{content}
      <div className={"rv in-card question" + (blockedBy ? " blocked" : "")} id={"rv-" + it.id}>
        <div className="qrow"><span className="ask">Your answer:</span>{it.suggested ? <button type="button" className="suggest-btn" onClick={() => p.onChange({ ...value, a: it.suggested })}>Use suggestion</button> : null}</div>
        <textarea ref={qa} className="qans" placeholder="Type your answer" value={value.a ?? ""} onChange={e => p.onChange({ ...value, a: e.target.value })} />
      </div>
    </section></>;

  if (type === "choice") {
    const first = p.choices?.[0]?.value, def = p.defaultChoice ?? "";
    const label = (x: string) => p.choices?.find(c => c.value === x)?.label ?? x;
    const pill = blocked ?? (state?.reopened && !v ? <Chip tone="reo">Reopened: {state.reopened}</Chip>
      : <Chip tone={v === first ? "a-yes" : ""}>{v ? label(v) : def ? `Not picked · ${label(def)} (default)` : "Not chosen"}</Chip>);
    return <>{group}
      <section data-item={it.id} data-review-question={it.id} data-title={it.title} data-answer={v ? (v === first ? "pick-first" : "pick") : "default"} className={"rvcard is-choice" + (blockedBy ? " is-blocked" : "")}>
        <div className="rvhead">{rid}<span className="sp" /><span className="st2" />{pill}</div>
        <h2>{n}. {it.title}</h2>{content}
        <div className={"rv in-card choice" + (blockedBy ? " blocked" : "")} id={"rv-" + it.id} data-choice={v || def}>
          <div className="rvrow"><span className="ask">Your answer:</span>
            <div className="seg" role="group" aria-label={"Answer for " + it.id}>
              {p.choices?.map((c, i) => { const isDef = !v && c.value === def; return <button key={c.value} type="button" data-v={c.value} aria-pressed={v === c.value} disabled={!!blockedBy}
                className={(i === 0 ? "first" : "other") + (isDef ? " def" : "")} onClick={() => p.onChange({ ...value, v: v === c.value ? "" : c.value })}>{c.label + (isDef ? " (default)" : "")}</button>; })}
            </div></div>
          <label className="notel"><span>Comments (optional)</span><textarea rows={2} disabled={!!blockedBy} value={note} onChange={e => p.onChange({ ...value, v, n: e.target.value })} /></label>
        </div>
      </section></>;
  }

  const showNote = v === "chg" || v === "no" || !!note.trim() || !!value.blocker || noteOpen || !!value.locked;
  const pill = blocked ?? (value.locked ? <Chip tone="skp">{PILL.skip}</Chip> : settled ? <Chip tone="a-yes">Yes (locked)</Chip> : v ? <Chip tone={TONE[v]}>{PILL[v]}</Chip>
    : state?.reopened ? <Chip tone="reo">Reopened: {state.reopened}</Chip> : handled ? <Chip tone="reo">Updated: answer again</Chip> : <Chip>Open</Chip>);
  const pick = (a: string) => {
    if (a === "skip") { if (!confirm("Skip this item? Once skipped it's locked and can't be changed.")) return; p.onChange({ v: "skip", n: note, locked: true }); return; }
    p.onChange({ ...value, v: a, n: note });
    if (a === "chg" && !note.trim()) setTimeout(() => ta.current?.focus());
  };
  return <>{group}
    <section data-item={it.id} data-review-question={it.id} data-title={it.title} data-answer={v}
      className={"rvcard" + (settled ? " settled" : "") + (shown ? " shown" : "") + (blockedBy ? " is-blocked" : "") + (value.blocker ? " is-blocker" : "")}>
      <div className="rvhead">{rid}
        {settled && <button type="button" className="settled-tg" aria-expanded={shown} onClick={() => flushSync(() => setShown(!shown))}>{shown ? "Hide" : "Show"}</button>}
        <span className="sp" />
        {value.blocker ? <span className="st bkr">Blocker</span> : state?.reopened && v && !blockedBy ? <span className="st reo">Reopened: {state.reopened}</span> : <span className="st2" />}
        {pill}{howBtn}
      </div>
      <h2>{n}. {it.title}</h2>{content}
      <div className={`rv in-card ${v}` + (locked ? " locked" : "") + (blockedBy ? " blocked" : "") + (value.blocker ? " blocker" : "") + (v === "chg" && !note.trim() ? " empty" : "")} id={"rv-" + it.id}>
        <div className="rvrow">
          <span className="ask">Your answer:</span>
          <Answer id={it.id} options={optionsFor(it, type)} value={v} disabled={locked} onChange={pick} />
          {!showNote && !blockedBy && <button type="button" className="add-note" disabled={locked} onClick={() => { setNoteOpen(true); setTimeout(() => ta.current?.focus()); }}>Add a note</button>}
          <span className="sp" />
          <button type="button" className="blocker-btn" disabled={!!held || settled} title={p.blockerTitle} onClick={() => {
            const typed = note.trim() || (prompt("What is blocking you? (one line)") ?? "").trim();
            if (typed) p.onBlocker(typed);
          }}>{p.blockerLabel}</button>
        </div>
        <label className="notel" hidden={!showNote}>
          <span><span className="nlt">{v === "chg" ? "What should change (required)" : v === "no" ? "Why (optional)" : "Note"}</span> <span className="need">Please say what to change.</span></span>
          <textarea ref={ta} rows={3} placeholder="Notes (required for Changes)" value={note} disabled={locked} onChange={e => p.onChange({ ...value, v, n: e.target.value })} />
        </label>
      </div>
    </section></>;
}

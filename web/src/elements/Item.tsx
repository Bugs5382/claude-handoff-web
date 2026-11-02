import { useState } from "react";
import { Answer, type AnswerOption } from "@/elements/Answer";
import { Blocks } from "@/elements/Blocks";
import { Chip } from "@/elements/Chip";
import type { ItemDef, ItemState, Local } from "@/lib/types";

const LABEL: Record<string, string> = { yes: "Yes", no: "No", changes: "Changes", skipped: "Skipped" };
const TONE: Record<string, string> = { yes: "a-yes", no: "a-no", changes: "a-chg", skipped: "skp" };

export const optionsFor = (it: ItemDef): AnswerOption[] =>
  (it.answers ?? ["yes", "no", "changes", ...(it.skip ? ["skipped"] : [])]).map(value => ({ value, label: LABEL[value] }));

export interface ItemProps {
  item: ItemDef;
  n: number;
  state?: ItemState;
  value: Local;
  locked?: boolean;
  diffs?: Record<string, string>;
  onChange: (next: Local) => void;
}

/** One numbered card: id, status, content, answers and the note box. */
export function Item({ item, n, state, value, locked, diffs, onChange }: ItemProps) {
  const [noteOpen, setNoteOpen] = useState(false);
  const settled = !!state?.hidden;
  const [shown, setShown] = useState(false);
  if ((item.type ?? "section") === "info") {
    return <section className="info" data-item={item.id}><h2>{n}. {item.title}</h2><Blocks blocks={item.body} id={item.id} diffs={diffs} /></section>;
  }
  const { answer, note } = value;
  const showNote = answer === "changes" || answer === "no" || !!note.trim() || noteOpen;
  const pill = settled ? <Chip tone="a-yes">Yes (locked)</Chip> : answer ? <Chip tone={TONE[answer]}>{LABEL[answer]}</Chip>
    : state?.reopened ? <Chip tone="reo">Reopened: {state.reopened}</Chip> : <Chip>Open</Chip>;
  return (
    <section data-item={item.id} data-review-question={item.id} data-title={item.title} data-answer={answer === "changes" ? "chg" : answer}
      className={"rvcard" + (settled ? " settled" : "") + (shown ? " shown" : "")}>
      <div className="rvhead">
        <a className="rid" href={"#rv-" + item.id} title={"Go to " + item.id}>{item.id}</a>
        {settled && <button type="button" className="settled-tg" aria-expanded={shown} onClick={() => setShown(!shown)}>{shown ? "Hide" : "Show"}</button>}
        <span className="sp" /><span className="st2" />{pill}
      </div>
      <h2>{n}. {item.title}</h2>
      <Blocks blocks={item.body} id={item.id} diffs={diffs} />
      <div className={"rv in-card" + (locked || settled ? " locked" : "")} id={"rv-" + item.id}>
        <div className="rvrow">
          <span className="ask">Your answer:</span>
          <Answer id={item.id} options={optionsFor(item)} value={answer} disabled={locked || settled} onChange={a => onChange({ answer: a, note })} />
          {!showNote && !locked && !settled && <button type="button" className="add-note" onClick={() => setNoteOpen(true)}>Add a note</button>}
        </div>
        <label className="notel" hidden={!showNote}>
          <span><span className="nlt">{answer === "changes" ? "What should change (required)" : answer === "no" ? "Why (optional)" : "Note"}</span></span>
          <textarea rows={3} placeholder="Notes (required for Changes)" value={note} disabled={locked || settled} onChange={e => onChange({ answer, note: e.target.value })} />
        </label>
      </div>
    </section>
  );
}

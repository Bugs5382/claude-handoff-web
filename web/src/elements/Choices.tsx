import { flushSync } from "react-dom";
import type { ItemChoice, Local } from "@/lib/types";

export interface ChoicesProps {
  id: string;
  title: string;
  options: ItemChoice[];
  /** Tick boxes for several picks, instead of one radio. */
  multi?: boolean;
  value: Local;
  disabled?: boolean;
  onChange: (next: Local) => void;
}

/** An item's own question: labelled options, the recommended one first, Other with its text, and an optional note. */
export function Choices({ id, title, options, multi, value, disabled, onChange }: ChoicesProps) {
  const picks = (value.v ?? "").split(",").filter(Boolean);
  const toggle = (v: string) => {
    const has = picks.includes(v);
    const next = multi ? (has ? picks.filter(p => p !== v) : [...options.map(o => o.value), "other"].filter(x => x === v || picks.includes(x))) : (has ? [] : [v]);
    flushSync(() => onChange({ ...value, v: next.join(",") }));
  };
  const row = (v: string, label: string, description?: string) => (
    <label className="rv-opt" key={v}>
      <input type={multi ? "checkbox" : "radio"} name={"choice-" + id} value={v} checked={picks.includes(v)} disabled={disabled} onChange={() => undefined} onClick={() => toggle(v)} />
      <span className="rv-opt-t"><span className="rv-opt-l">{label}</span>{description && <span className="rv-opt-d">{description}</span>}</span>
    </label>
  );
  return (
    <fieldset className="rv-opts" disabled={disabled}>
      <legend className="ask">{multi ? "Pick any that apply:" : "Pick one:"}</legend>
      {options.map(o => row(o.value, o.label + (o.recommended ? " (Recommended)" : ""), o.description))}
      {row("other", "Other")}
      {picks.includes("other") && <label className="rv-opt-other"><span>Your answer (required)</span>
        <input type="text" aria-label={"Other answer for " + title} value={value.o ?? ""} onChange={e => onChange({ ...value, o: e.target.value })} /></label>}
    </fieldset>
  );
}

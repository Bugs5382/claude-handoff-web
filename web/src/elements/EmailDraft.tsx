import { useState } from "react";
import { flushSync } from "react-dom";
import { stamp } from "@/lib/model";
import type { EmailVersion } from "@/lib/types";

export interface EmailDraftProps {
  id: string;
  versions: EmailVersion[];
  /** How many asks the agent hasn't answered yet. */
  waiting: boolean;
  to: string;
  /** Sends what's asked for. basedOn is the version it starts from. */
  onAsk: (ask: { instructions: string; prose: string; basedOn?: number }) => Promise<void>;
}

/** An item's email draft: every version, what produced each one, and asking for another. Answers never touch it. */
export function EmailDraft({ id, versions, waiting, to, onAsk }: EmailDraftProps) {
  const [picked, setPicked] = useState<number | null>(null);
  const [asking, setAsking] = useState(false);
  const [instructions, setInstructions] = useState("");
  const [prose, setProse] = useState("");
  const [busy, setBusy] = useState(false);
  const latest = versions[versions.length - 1];
  const shown = versions.find(v => v.n === picked) ?? latest;
  const ask = async () => {
    setBusy(true);
    try {
      await onAsk({ instructions: instructions.trim(), prose: prose.trim(), basedOn: shown?.n });
      setInstructions(""); setProse(""); setAsking(false);
    } catch (e) { alert("Couldn't ask for a draft: " + (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="email" data-email={id}>
      {shown && <>
        <div className="email-top"><span className="email-h">Email draft</span>
          {versions.length > 1 && <div className="seg email-vers" role="group" aria-label={"Versions of the draft for " + id}>
            {versions.map(v => <button key={v.n} type="button" aria-pressed={v.n === shown.n} onClick={() => flushSync(() => setPicked(v.n))}>v{v.n}</button>)}</div>}
        </div>
        <p className="muted email-meta">Version {shown.n} from {shown.from}, {stamp(shown.at)}{shown.basedOn ? `, based on version ${shown.basedOn}` : ""}</p>
        {shown.instructions && <p className="email-ask"><strong>Asked for:</strong> {shown.instructions}{shown.prose ? ` (${shown.prose})` : ""}</p>}
        {(shown.to || shown.subject) && <p className="email-head">{shown.to && <>To: {shown.to}<br /></>}{shown.subject && <>Subject: {shown.subject}</>}</p>}
        <div className="copyblk"><pre>{shown.body}</pre>
          <button type="button" className="copy-cmd" onClick={async e => { const b = e.currentTarget; await navigator.clipboard.writeText(shown.body); b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500); }}>Copy</button></div>
      </>}
      {waiting && <p className="muted email-wait">Waiting for {to} to send the draft.</p>}
      {asking ? <div className="email-form">
        <label>How to draft it<textarea rows={3} value={instructions} placeholder="Based on this step, what should the email do?" onChange={e => setInstructions(e.target.value)} /></label>
        <label>The prose you want<textarea rows={2} value={prose} placeholder="For example: plain, friendly, under 100 words" onChange={e => setProse(e.target.value)} /></label>
        <button type="button" className="email-send" disabled={busy || !instructions.trim()} onClick={() => void ask()}>{shown ? `Ask for another from version ${shown.n}` : "Ask for a draft"}</button>
        <button type="button" className="email-cancel" onClick={() => flushSync(() => setAsking(false))}>Cancel</button>
      </div> : <button type="button" className="email-open" onClick={() => flushSync(() => setAsking(true))}>{shown ? "Ask for another draft" : "Draft email"}</button>}
    </div>
  );
}

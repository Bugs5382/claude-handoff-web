import { useState } from "react";
import { flushSync } from "react-dom";
import { stamp } from "@/lib/model";
import type { EmailVersion } from "@/lib/types";

export interface EmailAsk { recipient?: string; ask?: string; tone?: string; change?: string; basedOn?: number }

export interface EmailDraftProps {
  id: string;
  versions: EmailVersion[];
  /** An ask the agent hasn't answered yet. */
  waiting: boolean;
  to: string;
  /** The form is open. The item's More button opens it. */
  asking: boolean;
  onClose: () => void;
  /** Sends what's asked for. The agent gets the step's data along with it. */
  onAsk: (ask: EmailAsk) => Promise<void>;
}

function Part({ label, text }: { label: string; text: string }) {
  return <div className="email-part">
    <div className="email-part-top"><span className="email-label">{label}</span>
      <button type="button" className="copy-cmd" aria-label={"Copy " + label} onClick={async e => { const b = e.currentTarget; await navigator.clipboard.writeText(text); b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500); }}>Copy</button></div>
    <pre>{text}</pre></div>;
}

/** An item's generated email: every version as To, Subject and Body, and asking for one. It never touches the answer. */
export function EmailDraft({ id, versions, waiting, to, asking, onClose, onAsk }: EmailDraftProps) {
  const [picked, setPicked] = useState<number | null>(null);
  const [recipient, setRecipient] = useState("");
  const [need, setNeed] = useState("");
  const [tone, setTone] = useState("");
  const [changing, setChanging] = useState(false);
  const [change, setChange] = useState("");
  const [busy, setBusy] = useState(false);
  const latest = versions[versions.length - 1];
  const shown = versions.find(v => v.n === picked) ?? latest;
  if (!shown && !waiting && !asking) return null;
  const send = async (ask: EmailAsk, done: () => void) => {
    setBusy(true);
    try { await onAsk(ask); done(); } catch (e) { alert("Couldn't ask for the email: " + (e as Error).message); } finally { setBusy(false); }
  };
  return (
    <div className="email" data-email={id}>
      <div className="email-top"><span className="email-h">{asking ? "Generate an email" : "Generated email"}</span>
        <span className="email-tools">
          {versions.length > 1 && <span className="seg email-vers" role="group" aria-label={"Versions of the email for " + id}>
            {versions.map(v => <button key={v.n} type="button" aria-pressed={v.n === shown?.n} onClick={() => flushSync(() => setPicked(v.n))}>v{v.n}</button>)}</span>}
          {asking && <button type="button" className="email-cancel" onClick={onClose}>Cancel</button>}
        </span>
      </div>
      {asking && <div className="email-form">
        <p className="email-help">Say who it's to and what you need from them. {to} already has this step, what changed and the comments, so don't retype them.</p>
        <label>Who is it to?<input value={recipient} placeholder="For example: the network team" onChange={e => setRecipient(e.target.value)} /></label>
        <label>What do you need from them?<textarea rows={2} value={need} placeholder="For example: confirm the updated switch list by Friday, or grant access to the three devices we couldn't reach" onChange={e => setNeed(e.target.value)} /></label>
        <label>Tone<input value={tone} placeholder="For example: plain and friendly" onChange={e => setTone(e.target.value)} /></label>
        <button type="button" className="email-send" disabled={busy || !recipient.trim() || !need.trim()} onClick={() => void send({ recipient: recipient.trim(), ask: need.trim(), tone: tone.trim() }, () => { setRecipient(""); setNeed(""); setTone(""); onClose(); })}>Generate email</button>
      </div>}
      {shown && <>
        <p className="muted email-meta">Version {shown.n} from {shown.from}, {stamp(shown.at)}{shown.basedOn ? `, based on version ${shown.basedOn}` : ""}</p>
        {(shown.ask || shown.change) && <p className="email-ask"><strong>Asked for:</strong> {shown.change ?? shown.ask}{shown.tone ? ` (${shown.tone})` : ""}</p>}
        {shown.to && <Part label="To" text={shown.to} />}
        {shown.subject && <Part label="Subject" text={shown.subject} />}
        <Part label="Body" text={shown.body} />
        {changing ? <div className="email-form">
          <label>What should change?<textarea rows={2} value={change} placeholder="For example: shorter, and name the two new switches" onChange={e => setChange(e.target.value)} /></label>
          <div className="email-actions"><button type="button" className="email-send" disabled={busy || !change.trim()} onClick={() => void send({ recipient: shown.to ?? "them", change: change.trim(), basedOn: shown.n }, () => { setChange(""); setChanging(false); })}>Generate a new version</button>
            <button type="button" className="email-cancel" onClick={() => flushSync(() => setChanging(false))}>Cancel</button></div>
        </div> : <div className="email-actions"><button type="button" className="email-change" onClick={() => flushSync(() => setChanging(true))}>Ask for changes</button></div>}
      </>}
      {waiting && <p className="muted email-wait">Waiting for {to} to send the email.</p>}
    </div>
  );
}

import { useState } from "react";
import { flushSync } from "react-dom";
import { cpName, deliveryOf, typeOf } from "@/lib/model";
import type { PageData } from "@/lib/types";
import { DeliveryLine } from "@/elements/Delivery";

export interface RestartProps { data: PageData; onRestart: (checkpoint: string) => Promise<void> }

/** A journey's restart from any checkpoint reached. It asks first, on the page. */
export function Restart({ data, onRestart }: RestartProps) {
  const p = data.page;
  const [cp, setCp] = useState("");
  const [busy, setBusy] = useState(false);
  const reached: string[] = [];
  for (const r of p.rounds) for (const c of Object.keys(r.checkpoints ?? {})) if (!reached.includes(c)) reached.push(c);
  if (!reached.length) return null;
  const stepOf = (c: string) => p.items.findIndex(it => it.checkpoint === c) + 1;
  const last = [...p.submissions].reverse().find(s => s.kind === "restart");
  const question = (c: string) => {
    const at = stepOf(c);
    const later = p.items.slice(at).filter(it => typeOf(p, it) === "step").map(it => p.items.indexOf(it) + 1);
    const steps = !later.length ? "Nothing after it changes" : later.length === 1 ? `Step ${later[0]} starts open again` : `Steps ${later[0]} to ${later[later.length - 1]} start open again`;
    return `Restart from ${cpName(c)}? ${steps}, and ${data.route.to} resets the environment first.`;
  };
  return <section className="rvrestart" aria-labelledby="restart-h">
    <h2 id="restart-h">Restart from a checkpoint</h2>
    <p className="restart-why">The steps up to the checkpoint stay Yes and later steps start open. {data.route.to} gets the restart and resets the environment.</p>
    <div className="restart-cps">{reached.map(c => <button key={c} type="button" data-cp={c} aria-pressed={cp === c} onClick={() => flushSync(() => setCp(c))}><span className="cp-name">{cpName(c)}</span><span className="cp-step">after step {stepOf(c)}</span></button>)}</div>
    <div className="restart-confirm" role="group" aria-label="Confirm the restart" hidden={!cp}>
      <p className="restart-q">{cp ? question(cp) : ""}</p>
      <button type="button" className="restart-go" disabled={busy} onClick={async () => { setBusy(true); try { await onRestart(cp); setCp(""); } catch (e) { alert("Couldn't restart: " + (e as Error).message); } finally { setBusy(false); } }}>{busy ? "Restarting…" : "Restart"}</button>
      <button type="button" className="restart-cancel" onClick={() => flushSync(() => setCp(""))}>Cancel</button>
    </div>
    {last ? <DeliveryLine dl={deliveryOf(data, last)} cls="restart-dlv" /> : null}
  </section>;
}

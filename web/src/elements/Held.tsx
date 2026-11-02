import { clock, deliveryOf, heldIds } from "@/lib/model";
import type { PageData, Submission } from "@/lib/types";

export interface HeldProps { data: PageData; sub: Submission; onUnlock: () => Promise<void> }

/** Where a Send stands, while what it carried waits on the agent. */
export function Held({ data, sub, onUnlock }: HeldProps) {
  const dl = deliveryOf(data, sub), to = dl.to, n = heldIds(data.page).length;
  const what = n === 1 ? "The item you sent is" : `The ${n} items you sent are`;
  const said = dl.state === "taken" ? `${to} picked this up at ${clock(sub.takenAt)}.`
    : dl.state === "deaf" ? `Saved to ${to}'s inbox at ${clock(sub.at)}, but ${to} isn't listening right now, so it may not be seen yet.`
      : `Sent to ${to} at ${clock(sub.at)}. It's in ${to}'s inbox, waiting to be picked up.`;
  return <section className="sentlock" data-state={dl.state} role="status"><span className="dlv-dot" aria-hidden="true" />
    <p><strong>{said}</strong> {what} locked until {to} updates this page. Everything else stays open.</p>
    <button type="button" className="unlock" onClick={e => { const b = e.currentTarget; b.disabled = true; void onUnlock().catch(err => { b.disabled = false; alert("Couldn't unlock: " + (err as Error).message); }); }}>Unlock to change an answer</button>
  </section>;
}

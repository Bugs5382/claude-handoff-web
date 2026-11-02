import type { ReactNode } from "react";
import { Phase } from "@/elements/Phase";
import { phaseOf } from "@/lib/model";
import type { ItemDef, Locals, PageData } from "@/lib/types";

export interface RoundProps {
  data: PageData;
  local: Locals;
  /** Draws one item: the template decides the heading. */
  item: (it: ItemDef, n: number | string) => ReactNode;
  /** Sends one phase. */
  sendPhase: (id: string) => void;
  sends: boolean;
  held: Set<string>;
  goTo: (id: string) => void;
}

/**
 * The round element, with its two templates. Round single is one set of items sent together, from the bar.
 * Round phases splits them into lettered phases, each with its own goal and Send.
 */
export function Round({ data, local, item, sendPhase, sends, held, goTo }: RoundProps) {
  const p = data.page;
  if (!p.phases) return <>{p.items.map((it, i) => item(it, i + 1))}</>;
  return <>{p.phases.map(ph => {
    const st = data.phases[ph.id];
    const items = p.items.filter(it => phaseOf(it.id) === ph.id);
    const answered = items.filter(it => local[it.id]?.v).length;
    const unsent = items.some(it => local[it.id]?.v && !held.has(it.id) && !data.states[it.id]?.hidden);
    const status = st.blocked ? <span className="st blk">Blocked by <a className="rid" href={"#phase-" + st.blocked} onClick={e => { e.preventDefault(); goTo(st.blocked as string); }}>{st.blocked}</a></span>
      : st.closed ? <span className="st a-yes">Closed</span> : <span className="st">{answered} of {items.length} answered</span>;
    return <Phase key={ph.id} id={ph.id} title={ph.title} goal={ph.goal} status={status}
      send={sends ? <button type="button" className="phase-send" disabled={!!st.blocked || !unsent} onClick={() => sendPhase(ph.id)}>Send phase {ph.id} to {data.route.to}</button> : undefined}>
      {items.map(it => item(it, ""))}
    </Phase>;
  })}</>;
}

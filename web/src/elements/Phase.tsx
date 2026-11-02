import type { ReactNode } from "react";

export interface PhaseProps {
  n: number;
  title: string;
  goal?: string;
  /** What's holding it, shown as Blocked by. */
  blockedBy?: string;
  /** The phase's own Send, and its items. */
  send?: ReactNode;
  children: ReactNode;
}

/** A part of a plan with its own goal and Send. */
export function Phase({ n, title, goal, blockedBy, send, children }: PhaseProps) {
  return <>
    <section className="phase">
      <h2 className="phase-h">Phase {n}: {title}</h2>
      {goal && <p className="phase-goal">{goal}</p>}
      {blockedBy && <p className="st blk">Blocked by {blockedBy}</p>}
      {send}
    </section>
    {children}
  </>;
}

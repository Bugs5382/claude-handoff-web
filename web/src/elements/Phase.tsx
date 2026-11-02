import type { ReactNode } from "react";

export interface PhaseProps {
  /** The letter, such as A, which is also what its steps start with. */
  id: string;
  title: string;
  goal?: string;
  /** Closed, Blocked by, or how far along it is. */
  status: ReactNode;
  /** The phase's own Send. */
  send?: ReactNode;
  children: ReactNode;
}

/** A part of a round with its own goal and Send. */
export function Phase({ id, title, goal, status, send, children }: PhaseProps) {
  return <>
    <section className="phase" id={"phase-" + id} data-phase={id}>
      <div className="phase-top"><h2 className="phase-h">Phase {id}: {title}</h2>{status}</div>
      {goal && <p className="phase-goal">{goal}</p>}
      {send}
    </section>
    {children}
  </>;
}

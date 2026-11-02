import type { ReactNode } from "react";

export interface FooterProps {
  /** The bar's state: done turns it green, approved adds the tick. */
  done: boolean;
  approved: boolean;
  status: string;
  saved: string;
  /** Row one: the jump controls. */
  jump: ReactNode;
  /** Row two: Send, Copy results and the rest. */
  children: ReactNode;
}

/** The bottom bar, as two rows. */
export function Footer({ done, approved, status, saved, jump, children }: FooterProps) {
  return (
    <div className={"rvbar two" + (done ? " all-done" : "") + (approved ? " approved" : "")} role="region" aria-label="Review progress">
      <div className="rvbar-in">
        <div className="rvbar-r1">{jump}
          <span className="stat"><span className="dot" aria-hidden="true" /><span className="cnt" role="status" aria-live="polite">{status}</span></span>
          <span className="svst" aria-live="polite">{saved}</span>
        </div>
        <div className="rvbar-r2">{children}</div>
      </div>
    </div>
  );
}

import type { ReactNode } from "react";

export interface ChipProps {
  /** The status pill's look: a-yes, a-no, a-chg, reo, blk, skp, or none for plain. */
  tone?: string;
  children: ReactNode;
}

export function Chip({ tone, children }: ChipProps) {
  return <span className={"st" + (tone ? " " + tone : "")} role="status">{children}</span>;
}

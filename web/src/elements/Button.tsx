import type { ReactNode } from "react";

export interface ButtonProps {
  /** The job it does, which is also its class: send-btn, copy, clear, blocker-btn, prev, next and the rest. */
  name: string;
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  title?: string;
}

export function Button({ name, children, onClick, disabled, title }: ButtonProps) {
  return <button type="button" className={name} onClick={onClick} disabled={disabled} title={title}>{children}</button>;
}

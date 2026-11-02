import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

export interface ItemAction {
  /** A stable name, which is also its data-action. */
  name: string;
  label: string;
  /** What it does, or href for a link. */
  onSelect?: () => void;
  href?: string;
  disabled?: boolean;
}

export interface ItemMoreProps {
  id: string;
  actions: ItemAction[];
}

/** One slot in a More menu: a button, or a link when the action has an href. */
export function ActionEntry({ action: a, onPick }: { action: ItemAction; onPick: () => void }) {
  if (a.href) return <a role="menuitem" data-action={a.name} href={a.href} onClick={onPick}>{a.label}</a>;
  return <button type="button" role="menuitem" data-action={a.name} disabled={a.disabled} onClick={() => { onPick(); a.onSelect?.(); }}>{a.label}</button>;
}

/** The More button on an item: it pops up that item's actions. Draws nothing when there are none. */
export function ItemMore({ id, actions }: ItemMoreProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("click", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("click", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  if (!actions.length) return null;
  return (
    <span className="item-more" ref={box}>
      <button type="button" className="item-more-btn" aria-haspopup="menu" aria-expanded={open} aria-label={"More for " + id} onClick={() => flushSync(() => setOpen(!open))}>More ▾</button>
      <span className="item-more-menu" role="menu" hidden={!open}>
        {actions.map(a => <ActionEntry key={a.name} action={a} onPick={() => flushSync(() => setOpen(false))} />)}
      </span>
    </span>
  );
}

import { useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

export interface ItemAction {
  /** A stable name, which is also its data-action. */
  name: string;
  label: string;
  onSelect: () => void;
  disabled?: boolean;
}

export interface ItemMoreProps {
  id: string;
  actions: ItemAction[];
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
        {actions.map(a => <button key={a.name} type="button" role="menuitem" data-action={a.name} disabled={a.disabled}
          onClick={() => { flushSync(() => setOpen(false)); a.onSelect(); }}>{a.label}</button>)}
      </span>
    </span>
  );
}

import { useEffect, useRef, useState } from "react";

export interface JumpItem { id: string; title: string }

export interface JumpBarProps {
  /** The open items, in page order. */
  open: JumpItem[];
  /** Everything's picked on a backlog, so it says so. */
  choicePage: boolean;
  goTo: (id: string) => void;
}

const MAX_ROWS = 200;

function step(open: JumpItem[], dir: number, goTo: (id: string) => void) {
  if (!open.length) return;
  const y = window.scrollY + 80;
  const pos = open.map(it => (document.querySelector(`[data-review-question="${CSS.escape(it.id)}"]`) as HTMLElement).getBoundingClientRect().top + window.scrollY);
  let i = dir > 0 ? pos.findIndex(t => t > y + 5) : pos.map(t => t < y - 5).lastIndexOf(true);
  if (i < 0) i = dir > 0 ? 0 : open.length - 1;
  goTo(open[i].id);
}

/** Previous and Next, with the n and p keys. */
export function JumpBar({ open, goTo }: Omit<JumpBarProps, "choicePage">) {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement | null)?.tagName ?? "")) return;
      if (e.key === "n") step(open, 1, goTo); else if (e.key === "p") step(open, -1, goTo);
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, goTo]);
  return <>
    <button className="prev" type="button" title="Previous open item (p)" aria-label="Previous open item" onClick={() => step(open, -1, goTo)}>← <span className="lg">Previous</span><span className="sm">Prev</span></button>
    <button className="next" type="button" title="Next open item (n)" aria-label="Next open item" onClick={() => step(open, 1, goTo)}>Next →</button>
  </>;
}

export interface OpenIdsProps extends JumpBarProps { shown: boolean; onClose: () => void }

/** The Open IDs picker: it opens upward, with a filter. */
export function OpenIds({ open, choicePage, goTo, shown, onClose }: OpenIdsProps) {
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { if (shown) { setQ(""); setActive(0); input.current?.focus(); } }, [shown]);
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hit = words.length ? open.filter(it => words.every(w => (it.id + " " + it.title).toLowerCase().includes(w))) : open;
  const rows = hit.slice(0, MAX_ROWS), at = Math.min(active, Math.max(0, rows.length - 1));
  const noun = choicePage ? "not picked" : "open";
  const pick = (id: string) => { onClose(); goTo(id); };
  return (
    <div className="rvpop rvids" role="dialog" aria-label="Open IDs" hidden={!shown}>
      <label className="rvids-l"><span className="rvids-h">{`${choicePage ? "Jump to an item you haven't picked" : "Jump to an open item"} · ${open.length.toLocaleString("en-US")} ${noun} · showing ${rows.length.toLocaleString("en-US")}`}</span>
        <input ref={input} type="search" autoComplete="off" spellCheck={false} placeholder="Type an ID or words from the title" value={q} aria-activedescendant={rows.length ? "rvpick-" + at : undefined}
          onChange={e => { setQ(e.target.value); setActive(0); }}
          onKeyDown={e => {
            if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); if (rows.length) setActive((at + (e.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length); }
            else if (e.key === "Enter") { e.preventDefault(); if (rows[at]) pick(rows[at].id); }
          }} /></label>
      <div className="rvids-list" role="listbox">
        {rows.map((it, i) => <a key={it.id} href={"#rv-" + it.id} role="option" id={"rvpick-" + i} className={i === at ? "on" : undefined} aria-selected={i === at || undefined}
          onClick={e => { e.preventDefault(); pick(it.id); }}><span className="i">{it.id}</span><span className="x">{it.title}</span></a>)}
        {!open.length ? <span className="none">{choicePage ? "Every item is picked" : "Nothing open"}</span>
          : !hit.length ? <span className="nomatch">{choicePage ? "No unpicked item matches" : "No open item matches"}</span>
            : hit.length > rows.length ? <span className="more-n">{(hit.length - rows.length).toLocaleString("en-US")} more · keep typing to narrow it</span> : null}
      </div>
      <div className="rvids-keys"><span>↑↓ move</span><span>Enter jump</span><span>Esc close</span><span>n / p next, previous</span></div>
    </div>
  );
}

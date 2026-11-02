import { Button } from "@/elements/Button";

export interface JumpBarProps {
  /** The open items' ids, in page order. */
  open: string[];
}

function go(ids: string[], dir: number) {
  if (!ids.length) return;
  const y = window.scrollY + 80;
  const tops = ids.map(id => (document.querySelector(`[data-review-question="${CSS.escape(id)}"]`) as HTMLElement).getBoundingClientRect().top + window.scrollY);
  let i = dir > 0 ? tops.findIndex(t => t > y + 5) : tops.map(t => t < y - 5).lastIndexOf(true);
  if (i < 0) i = dir > 0 ? 0 : ids.length - 1;
  window.scrollTo({ top: tops[i] - 16, behavior: "smooth" });
}

/** Previous and Next, walking the open items. */
export function JumpBar({ open }: JumpBarProps) {
  return <>
    <Button name="prev" onClick={() => go(open, -1)} title="Previous open item">← Previous</Button>
    <Button name="next" onClick={() => go(open, 1)} title="Next open item">Next →</Button>
  </>;
}

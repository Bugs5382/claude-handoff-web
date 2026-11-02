import { useState } from "react";
import type { Round } from "@/lib/types";

export interface HistoryRow { round: Round; count: string }

function RoundRow({ round: r, count }: HistoryRow) {
  const [copied, setCopied] = useState(false);
  const text = r.results ?? "";
  return <details className="rvhist-round">
    <summary>{`Round ${r.round}${r.build ? " · build " + r.build : ""} · ${(r.closed ?? "").slice(0, 10)} · ${count}`}</summary>
    <pre className="hist-text">{text}</pre>
    <button type="button" className="hist-copy" onClick={async () => { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy results"}</button>
  </details>;
}

/** Closed rounds, collapsed, after the page's own content. */
export function History({ rows }: { rows: HistoryRow[] }) {
  return <details className="rvhist" id="rvhist"><summary>{`History (${rows.length}${rows.length === 1 ? " round" : " rounds"})`}</summary>
    {rows.map(r => <RoundRow key={r.round.round} {...r} />)}</details>;
}

import { useEffect, useMemo } from "react";
import { Button } from "@/elements/Button";
import { Footer } from "@/elements/Footer";
import { Item } from "@/elements/Item";
import { JumpBar } from "@/elements/JumpBar";
import { count } from "@/lib/count";
import { rel } from "@/lib/api";
import { usePage } from "@/lib/usePage";
import type { ItemDef, Local, PageData } from "@/lib/types";

const LOUD: Record<string, string> = { yes: "YES", no: "NO", changes: "CHANGES", skipped: "SKIPPED (locked)" };

export function resultsOf(data: PageData, items: ItemDef[], local: Record<string, Local>): string {
  const lines = items.map(it => {
    const l = local[it.id];
    return `- [${it.id}] ${LOUD[l?.answer ?? ""] ?? "NOT ANSWERED"}: ${it.title}` + (l?.note ? `\n    Note: ${l.note.replace(/\n/g, " ")}` : "");
  });
  const yes = items.filter(it => local[it.id]?.answer === "yes").length;
  return `Review: ${data.page.title} (/${rel})\n${lines.join("\n")}\n\n` + (yes === items.length ? "APPROVED: every item is Yes." : `Not approved yet: ${yes} of ${items.length} are Yes.`) + "\n";
}

/** A whole page file: the header, its items in order and the bar. */
export function Page() {
  const { data, local, saved, setAnswer, send } = usePage();
  useEffect(() => { if (data) document.title = data.page.title; }, [data]);
  const items = useMemo(() => (data ? data.page.items.filter(it => (it.type ?? "section") !== "info") : []), [data]);
  if (!data) return <main className="wrap" id="page"><p className="muted">Loading…</p></main>;
  const hidden = new Set(Object.entries(data.states).filter(([, s]) => s.hidden).map(([id]) => id));
  const c = count(items, local, hidden);
  const status = c.approved ? `APPROVED · all ${c.total} Yes` : `${c.answered} of ${c.total} answered` + (c.hidden ? ` · ${c.hidden} approved and locked` : "");
  const results = resultsOf(data, items, local);
  const sends = data.route.mode !== "copy";
  return <>
    <header className="top"><div className="wrap"><h1>{data.page.title}</h1>{data.page.summary && <p>{data.page.summary}</p>}</div></header>
    <main className="wrap" id="page">
      {data.page.items.map((it, i) => (
        <Item key={it.id} item={it} n={i + 1} state={data.states[it.id]} value={local[it.id] ?? { answer: "", note: "" }} diffs={data.diffs} onChange={next => setAnswer(it.id, next)} />
      ))}
    </main>
    <Footer done={c.allDone} approved={c.approved} status={status} saved={saved} jump={<JumpBar open={c.openIds} />}>
      {sends && <Button name="send-btn" onClick={() => void send(results)}>Send to {data.route.to}</Button>}
      <Button name="copy" onClick={() => void navigator.clipboard.writeText(results)}>Copy results</Button>
    </Footer>
  </>;
}

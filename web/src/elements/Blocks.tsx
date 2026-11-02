import { inline } from "@/lib/text";
import type { Block } from "@/lib/types";

const Inline = ({ text }: { text: unknown }) => <span dangerouslySetInnerHTML={{ __html: inline(text) }} />;

function One({ block: b, diff }: { block: Block; diff?: string }) {
  if ("p" in b) return <p><Inline text={b.p} /></p>;
  if ("list" in b) return <ul>{(b.list as string[]).map((x, i) => <li key={i}><Inline text={x} /></li>)}</ul>;
  if ("olist" in b) return <ol>{(b.olist as string[]).map((x, i) => <li key={i}><Inline text={x} /></li>)}</ol>;
  if ("code" in b) return <pre>{String(b.code)}</pre>;
  if ("note" in b) return <p className={"note " + String(b.tone ?? "info")}><Inline text={b.note} /></p>;
  if ("copy" in b) return <div className="copyblk"><pre>{String(b.copy)}</pre></div>;
  if ("diff" in b) return <div dangerouslySetInnerHTML={{ __html: diff ?? "" }} />;
  if ("table" in b) {
    const [head, ...rows] = b.table as string[][];
    return <table><thead><tr>{head.map((c, i) => <th key={i}><Inline text={c} /></th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody></table>;
  }
  return null;
}

export interface BlocksProps { blocks?: Block[]; id: string; diffs?: Record<string, string> }

export function Blocks({ blocks, id, diffs }: BlocksProps) {
  return <>{(blocks ?? []).map((b, i) => <One key={i} block={b} diff={diffs?.[`${id}/body/${i + 1}`]} />)}</>;
}

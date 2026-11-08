import { inline } from "@/lib/text";
import type { Block, Field, ItemDef } from "@/lib/types";

const Inline = ({ text }: { text: unknown }) => <span dangerouslySetInnerHTML={{ __html: inline(text, { copy: true }) }} />;

function CopyBlock({ text }: { text: string }) {
  return <div className="copyblk"><pre>{text}</pre>
    <button type="button" className="copy-cmd" onClick={async e => {
      const b = e.currentTarget;
      await navigator.clipboard.writeText(text); b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500);
    }}>Copy</button></div>;
}

export function Picture({ src, alt, caption }: { src: string; alt?: string; caption?: string }) {
  return <><a href={src} target="_blank" rel="noopener"><img src={src} alt={alt ?? ""} width={320} /></a>
    {caption ? <><br /><span className="muted"><Inline text={caption} /></span></> : null}</>;
}

export function FieldsTable({ fields }: { fields: Field[] }) {
  return <table><thead><tr><th>Name</th><th>Type</th><th>Rule</th></tr></thead><tbody>
    {fields.map((f, i) => <tr key={i}><td><Inline text={f.name} /></td><td><Inline text={f.type} /></td><td><Inline text={f.rule} /></td></tr>)}</tbody></table>;
}

function One({ block: b, diff, copyCode }: { block: Block; diff?: string; copyCode?: boolean }) {
  if ("p" in b) return <p><Inline text={b.p} /></p>;
  if ("list" in b) return <ul>{(b.list as string[]).map((x, i) => <li key={i}><Inline text={x} /></li>)}</ul>;
  if ("olist" in b) return <ol>{(b.olist as string[]).map((x, i) => <li key={i}><Inline text={x} /></li>)}</ol>;
  if ("code" in b) return copyCode ? <CopyBlock text={String(b.code)} /> : <pre>{String(b.code)}</pre>;
  if ("note" in b) return <p className={"note " + String(b.tone ?? "info")}><Inline text={b.note} /></p>;
  if ("copy" in b) return <CopyBlock text={String(b.copy)} />;
  if ("diff" in b) return <div dangerouslySetInnerHTML={{ __html: diff ?? "" }} />;
  if ("image" in b) return <p><Picture src={String(b.image)} alt={b.alt as string} caption={b.caption as string} /></p>;
  if ("html" in b) return <div className="raw-html" data-flagged="unconverted" dangerouslySetInnerHTML={{ __html: String(b.html) }} />;
  if ("table" in b) {
    const [head, ...rows] = b.table as string[][];
    return <table><thead><tr>{head.map((c, i) => <th key={i}><Inline text={c} /></th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody></table>;
  }
  return null;
}

export interface BlocksProps { blocks?: Block[]; id: string; part?: string; diffs?: Record<string, string> }

/** A list of body blocks. Pictures in a row with no caption share one paragraph. */
export function Blocks({ blocks, id, part = "body", diffs }: BlocksProps) {
  const out: React.ReactNode[] = [];
  let row: Block[] = [];
  const flush = (k: number) => { if (row.length) { const r = row; out.push(<p key={"r" + k}>{r.map((b, i) => <span key={i}><Picture src={String(b.image)} alt={b.alt as string} />{" "}</span>)}</p>); row = []; } };
  (blocks ?? []).forEach((b, i) => {
    if ("image" in b && !b.caption) { row.push(b); return; }
    flush(i); out.push(<One key={i} block={b} diff={diffs?.[`${id}/${part}/${i + 1}`]} copyCode={part === "howto"} />);
  });
  flush(-1);
  return <>{out}</>;
}

export const ItemExtras = ({ item: it, diffs, isDiff }: { item: ItemDef; diffs?: Record<string, string>; isDiff: boolean }) => <>
  {it.steps && <ol>{it.steps.map((s, i) => <li key={i}><Inline text={s} /></li>)}</ol>}
  {isDiff && <div dangerouslySetInnerHTML={{ __html: diffs?.[it.id] ?? "" }} />}
  {it.images?.map((im, i) => <p key={i}><Picture {...im} /></p>)}
  {it.fields && <FieldsTable fields={it.fields} />}
  {it.forms?.map((f, i) => <div key={i}><p><strong>{f.name}</strong></p><FieldsTable fields={f.fields ?? []} /></div>)}
</>;

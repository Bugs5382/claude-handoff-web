import type { Delivery } from "@/lib/model";

export function DeliveryLine({ dl, cls }: { dl: Delivery; cls: string }) {
  return <p className={cls} data-state={dl.state} aria-live="polite"><span className="dlv-dot" aria-hidden="true" />
    {dl.state === "replied" ? <a className="dlv-t" href="#replies" title={dl.full}>{dl.text}</a> : <span className="dlv-t">{dl.text}</span>}</p>;
}

/** The bar's delivery state: a dot, the line, and on "isn't listening" a Copy results button. */
export function BarDelivery({ dl, onCopy }: { dl: Delivery | null; onCopy: () => Promise<void> }) {
  if (!dl) return <span className="dlv" role="status" aria-live="polite" />;
  return <span className="dlv" role="status" aria-live="polite" data-state={dl.state}><span className="dlv-dot" aria-hidden="true" />
    {dl.state === "replied" ? <a className="dlv-t" href="#replies" title={dl.full ?? dl.text}>{dl.bar ?? dl.text}</a> : <span className="dlv-t" title={dl.text}>{dl.bar ?? dl.text}</span>}
    {dl.state === "deaf" && <button type="button" className="dlv-copy" onClick={e => { const b = e.currentTarget; void onCopy().then(() => { b.textContent = "Copied"; }); }}>Copy results instead</button>}
  </span>;
}

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { BarDelivery } from "@/elements/Delivery";
import { EmailDraft } from "@/elements/EmailDraft";
import { Footer } from "@/elements/Footer";
import { Held } from "@/elements/Held";
import { History } from "@/elements/History";
import { Item } from "@/elements/Item";
import { JumpBar, OpenIds } from "@/elements/JumpBar";
import { Restart } from "@/elements/Restart";
import { Round } from "@/elements/Round";
import { Thread, itemEntries, replyEntry } from "@/elements/Thread";
import { postPage, rel } from "@/lib/api";
import { wireDiffs } from "@/lib/diffs";
import { actToast, returnSoon } from "@/lib/finish";
import { folder, folderPages, folderUrl } from "@/lib/howto";
import { DONE, blockers, count, deliveryOf, heldBy, heldIds, openRound, typeOf, type CountItem } from "@/lib/model";
import { templates } from "@/lib/custom";
import { inline } from "@/lib/text";
import { usePage } from "@/lib/usePage";
import type { ItemDef, Locals, PageData } from "@/lib/types";

const LOUD: Record<string, string> = { yes: "YES", no: "NO", chg: "CHANGES", skip: "SKIPPED (locked)", risk: "ACCEPT RISK" };

function tally(data: PageData, items: ItemDef[], s: Locals): string {
  const opts = data.page.options?.choices ?? [], def = data.page.options?.default ?? "";
  return opts.map(o => `${items.filter(it => (s[it.id]?.v || def) === o.value).length} ${o.label.toLowerCase()}`).join(" · ");
}

export function resultsOf(data: PageData, s: Locals, blocked: Record<string, string>): string {
  const p = data.page, t = (it: ItemDef) => typeOf(p, it);
  const answerable = p.items.filter(it => t(it) !== "info");
  const qs = answerable.filter(it => t(it) === "question"), choices = answerable.filter(it => t(it) === "choice");
  const label = (v: string) => p.options?.choices.find(c => c.value === v)?.label ?? v;
  let out = `Review: ${p.title} (/${rel})\n`;
  for (const it of answerable.filter(x => t(x) !== "question")) {
    const l = s[it.id] ?? {}, pick = l.v || p.options?.default || "";
    const ans = t(it) === "choice" ? (pick ? label(pick).toUpperCase() : "NOT ANSWERED") : (LOUD[l.v ?? ""] ?? "NOT ANSWERED");
    out += `- [${it.id}] ${blocked[it.id] ? `BLOCKED by ${blocked[it.id]}, ` : ""}${l.blocker ? "BLOCKER, " : ""}${ans}: ${it.title}${l.n ? `\n    Note: ${l.n.replace(/\n/g, " ")}` : ""}\n`;
  }
  const ync = answerable.filter(it => t(it) !== "question" && t(it) !== "choice");
  const counted = ync.filter(it => !s[it.id]?.locked), yes = counted.filter(it => DONE.includes(s[it.id]?.v ?? "")).length;
  out += "\n";
  if (counted.length || !choices.length) out += (yes === counted.length ? `APPROVED: every item is Yes${p.kind === "round" ? " or Accept risk" : ""}.` : `Not approved yet: ${yes} of ${counted.length} are Yes.`) + "\n";
  if (choices.length) out += tally(data, choices, s) + "\n";
  const qOpen = qs.filter(it => !(s[it.id]?.a ?? "").trim()).length;
  if (qOpen) out += `${qOpen} open question${qOpen === 1 ? "" : "s"}\n`;
  if (qs.length) { out += "\n"; for (const it of qs) out += `Q ${it.id}: ${(s[it.id]?.a ?? "").trim().replace(/\n/g, " ") || "(no answer)"}\n`; }
  return out;
}

const hhmm = (at: Date) => at.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** A whole page file: the header, its items in order and the bar. */
export function Page() {
  const pg = usePage();
  const { data, local, set, flush, redraw } = pg;
  const [popup, showPopup] = useState<"" | "menu" | "ids">("");
  const setPopup = useCallback((v: "" | "menu" | "ids") => flushSync(() => showPopup(v)), []);
  const wasDone = useRef<boolean | null>(null);
  const live = useRef(local);
  live.current = local;

  const goTo = useCallback((id: string) => {
    const el = (document.querySelector(`[data-review-question="${CSS.escape(id)}"]`) ?? document.getElementById("phase-" + id)) as HTMLElement | null;
    if (!el) return;
    if (el.classList.contains("settled") && !el.classList.contains("shown")) (el.querySelector(".settled-tg") as HTMLElement).click();
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    const f = el.querySelector<HTMLElement>(".seg button:not(:disabled), textarea:not(:disabled)");
    if (f) setTimeout(() => f.focus({ preventScroll: true }), 400);
  }, []);

  useLayoutEffect(() => {
    if (!data) return;
    document.dispatchEvent(new CustomEvent("handoff:page", { detail: { data } }));
    wireDiffs();
    const toggle = document.querySelector(".theme-tg.floating"), header = document.querySelector("header.top");
    if (toggle && header) { toggle.classList.remove("floating"); header.appendChild(toggle); }
  }, [data]);
  useEffect(() => {
    const close = (e: Event) => { if (!(e.target as Element).closest?.(".rvbar")) setPopup(""); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setPopup(""); };
    document.addEventListener("click", close); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("click", close); document.removeEventListener("keydown", esc); };
  }, [setPopup]);

  const model = useMemo(() => {
    if (!data) return null;
    const p = data.page, r = openRound(p);
    const blocked = blockers(data);
    const hidden = new Set(p.items.filter(it => data.states[it.id]?.hidden && typeOf(p, it) !== "choice").map(it => it.id));
    const kinds: CountItem[] = p.items.filter(it => typeOf(p, it) !== "info").map(it => { const t = typeOf(p, it); return { id: it.id, kind: t === "question" ? "question" : t === "choice" ? "choice" : "ync" }; });
    return { p, r, blocked, hidden, kinds, held: new Set(heldIds(p)), sub: heldBy(p) };
  }, [data]);

  const results = useCallback(() => (data && model ? resultsOf(data, live.current, model.blocked) : ""), [data, model]);
  useEffect(() => {
    (window as unknown as { siteReview: unknown }).siteReview = { results, unsaved: pg.unsaved, state: () => live.current, flushNow: flush };
  }, [results, pg.unsaved, flush]);

  const c = model ? count(model.kinds, local, model.hidden, model.blocked) : null;
  useEffect(() => {
    if (!c) return;
    if (wasDone.current === false && c.allDone && folder) actToast((c.approved ? "Approved." : "Every item answered.") + " Copy results from More, then", "back to " + folderPages);
    wasDone.current = c.allDone;
  });

  if (!data || !model || !c) return <main className="wrap" id="page"><p className="muted">{pg.saved || "Loading…"}</p></main>;
  const { p, r, blocked, hidden, held, sub } = model;
  const sends = data.route.mode !== "copy", to = data.route.to;
  const reference = p.kind === "reference" || p.kind === "status";
  const copy = async () => { await navigator.clipboard.writeText(results()); };
  const sendAll = async () => {
    const left = c.total - c.answered;
    if (!c.allDone && !confirm(`Send now? ${left} item${left === 1 ? " is" : "s are"} still open.`)) return;
    if (!(await flush())) { alert("Can't send yet: the answers aren't saved. Try again once it says Saved."); return; }
    try { await postPage("/send", { kind: "send", results: results() }); await redraw(); } catch (e) { alert(`Couldn't send: ${(e as Error).message}. Use Copy results instead.`); }
  };
  const sendPhase = async (id: string) => {
    const open = data.phases[id].items.filter(x => c.openIds.includes(x)).length;
    if (open && !confirm(`Send phase ${id} now? ${open} item${open === 1 ? " is" : "s are"} still open.`)) return;
    if (!(await flush())) { alert("Can't send yet: the answers aren't saved. Try again once it says Saved."); return; }
    try { await postPage("/send", { kind: "send", phase: id, results: results() }); await redraw(); } catch (e) { alert(`Couldn't send: ${(e as Error).message}. Use Copy results instead.`); }
  };
  const emailFor = (it: ItemDef) => {
    const versions = p.emails?.[it.id] ?? [];
    if (!p.drafts && !versions.length) return undefined;
    const asked = p.submissions.filter(s => s.kind === "email" && s.items.includes(it.id) && s.state !== "failed").length;
    return <EmailDraft id={it.id} versions={versions} waiting={asked > versions.length} to={to}
      onAsk={async ask => { await postPage("/send", { kind: "email", items: [it.id], ...ask }); await redraw(); }} />;
  };
  const deck = async () => {
    const framing = (prompt("What are you trying to build? For example: a presentation on the network migration timeline and risks") ?? "").trim();
    if (!framing) return;
    if (!(await flush())) { alert("Can't send yet: the answers aren't saved. Try again once it says Saved."); return; }
    if (!sends) {
      const final = p.items.filter(it => DONE.includes(local[it.id]?.v ?? ""));
      await navigator.clipboard.writeText(`Build a deck: ${framing}\n${final.map(it => `- [${it.id}] ${it.title}${local[it.id]?.n ? ` (${local[it.id]?.n})` : ""}`).join("\n")}\n`);
      alert("Copied what the deck needs. Paste it to " + to + ".");
      return;
    }
    try { await postPage("/send", { kind: "deck", framing, results: results() }); await redraw(); alert(`Sent to ${to}. The link comes back on this page.`); }
    catch (e) { alert("Couldn't ask for the deck: " + (e as Error).message); }
  };
  const blocker = async (it: ItemDef, note: string) => {
    const cur = local[it.id] ?? {};
    set(it.id, { ...cur, n: note, blocker: true });
    const out = `BLOCKER: ${p.title} (/${rel}${p.build ? ", build " + p.build : ""})\n- [${it.id}] ${it.title}\n    Note: ${note.replace(/\n/g, " ")}\n`;
    if (!sends) { await navigator.clipboard.writeText(out); alert(`Blocker copied. Paste it to ${to} now.`); return; }
    try {
      if (!(await flush())) throw new Error("the answers aren't saved yet");
      const sent = await postPage("/send", { kind: "blocker", items: [it.id], results: out }) as { to: string; listening: boolean };
      await redraw();
      alert(`Blocker sent to ${sent.to}.` + (sent.listening ? "" : ` ${sent.to} isn't listening right now, so paste it to them as well.`));
      if (!sent.listening) await navigator.clipboard.writeText(out);
    } catch (e) {
      await navigator.clipboard.writeText(out);
      alert(`Couldn't send the blocker (${(e as Error).message}), so it's copied. Paste it to ${to} now.`);
    }
  };
  const markAll = (v: string, label: string) => {
    setPopup("");
    const open = p.items.filter(it => { const t = typeOf(p, it); return t !== "info" && t !== "question" && t !== "choice" && !hidden.has(it.id) && !blocked[it.id] && !local[it.id]?.locked && !local[it.id]?.v && (!it.answers || it.answers.map(a => a === "changes" ? "chg" : a).includes(v)); });
    if (!open.length) { alert("Every item already has an answer."); return; }
    if (!confirm(`Mark the ${open.length} unanswered item${open.length === 1 ? "" : "s"} ${label}? Items you've answered keep their answers.`)) return;
    for (const it of open) set(it.id, { ...local[it.id], v, n: local[it.id]?.n ?? "" });
  };
  const clear = async () => {
    setPopup("");
    if (!confirm("Clear your answers on this page? Approved and Skipped (locked) items stay.")) return;
    for (const it of p.items) if (typeOf(p, it) !== "info" && !hidden.has(it.id) && !local[it.id]?.locked) set(it.id, {});
    if (await flush()) await redraw();
  };
  const copyBlockers = async () => {
    setPopup("");
    const list = p.items.filter(it => !hidden.has(it.id) && local[it.id]?.blocker);
    if (!list.length) { alert("No item on this page is marked as a blocker."); return; }
    let out = `BLOCKER: ${p.title} (/${rel}${p.build ? ", build " + p.build : ""})\n`;
    for (const it of list) out += `- [${it.id}] ${it.title}\n    Note: ${(local[it.id]?.n ?? "").replace(/\n/g, " ")}\n`;
    await navigator.clipboard.writeText(out);
    alert(`${list.length}${list.length === 1 ? " blocker" : " blockers"} copied. Paste ${list.length === 1 ? "it" : "them"} to ${to} now.`);
  };
  const roundClose = async () => {
    setPopup("");
    if (!confirm("Save this round to history now? The next change starts a new round.")) return;
    if (!(await flush())) { alert("Can't save yet: the box can't be reached. Try again once it says Saved."); return; }
    try { const out = await postPage("/round", { results: results() }) as { round: number }; await redraw(); alert(`Saved as Round ${out.round - 1}.`); } catch (e) { alert("Couldn't save the round: " + (e as Error).message); }
  };

  const choices = p.items.filter(it => typeOf(p, it) === "choice");
  const tl = choices.length ? tally(data, choices, local) : "";
  const qTail = c.qOpen ? ` · ${c.qOpen} question${c.qOpen === 1 ? "" : "s"} unanswered` : "";
  const tails = (c.blocked ? ` · ${c.blocked} blocked` : "") + (c.skipped ? ` · ${c.skipped} skipped` : "") + (c.hidden ? ` · ${c.hidden} approved and locked` : "") + (tl && !c.choiceOnly ? " · " + tl : "") + qTail;
  const text = c.choiceOnly ? (c.allDone ? `All ${c.total} picked` : `${c.answered} of ${c.total} picked`) + (tl ? " · " + tl : "") + qTail
    : c.approved ? `APPROVED · all ${c.yncTotal || c.hidden} Yes` + (c.yncTotal && c.hidden ? ` · ${c.hidden} approved and locked` : "") + (tl ? " · " + tl : "") + qTail
      : c.allDone ? `All ${c.total} answered · ready to copy` + tails : `${c.answered} of ${c.total} answered` + tails;
  const unsent = model.kinds.some(({ id }) => !held.has(id) && !hidden.has(id) && (local[id]?.v || (local[id]?.a ?? "").trim()));
  const sendDone = !!sub && !unsent;
  const openItems = c.openIds.map(id => { const it = p.items.find(x => x.id === id) as ItemDef; return { id, title: it.title }; });
  const choicePage = choices.length > 0 && !model.kinds.some(k => k.kind === "ync");
  const lastSend = [...p.submissions].reverse().find(s => s.kind !== "restart" && s.kind !== "email");
  const delivery = sends ? <BarDelivery dl={lastSend ? deliveryOf(data, lastSend) : null} onCopy={copy} /> : undefined;
  const closed = p.rounds.filter(x => x.closed);
  const rows = closed.map(round => {
    const items = p.items.filter(it => !["info", "question", "choice"].includes(typeOf(p, it)));
    const yes = items.filter(it => round.answers[it.id]?.answer === "yes").length;
    return { round, count: items.length ? `${yes} of ${items.length} Yes` : "no items" };
  }).reverse();
  const flags = [c.allDone && "all-done", c.approved && "approved", c.blockers > 0 && "has-blocker", pg.bad && "save-bad"].filter(Boolean).join(" ");
  const pageReplies = (p.thread._page ?? []).map(replyEntry);

  const renderItem = (it: ItemDef, n: number | string) => (
        <Item key={it.id} item={it} n={n} risk={p.kind === "round"} type={typeOf(p, it)} state={data.states[it.id]} value={local[it.id] ?? {}} blockedBy={blocked[it.id]} held={held.has(it.id)}
          handled={!!r.handled?.[it.id]} entries={itemEntries(data, it.id)} email={emailFor(it)} diffs={data.diffs} build={p.build} choices={p.options?.choices} defaultChoice={p.options?.default}
          blockerLabel={sends ? "Blocker: send now" : "Blocker: copy now"}
          blockerTitle={`Something stops you testing or using it: ${sends ? "send this one item to" : "copy this one item and paste it to"} ${to} straight away`}
          isItem={id => p.items.some(x => x.id === id) || !!data.phases[id]} goTo={goTo} onChange={next => set(it.id, next)} onBlocker={note => void blocker(it, note)} />
  );
  const custom = p.template ? templates[p.template] : undefined;
  const body = (item: typeof renderItem) => custom
    ? custom({ data, local, item, sendPhase: id => void sendPhase(id), goTo })
    : <Round data={data} local={local} sends={sends} held={held} goTo={goTo} sendPhase={id => void sendPhase(id)} item={item} />;
  const footer = reference ? null : (<Footer alwaysTwo={!!p.deck} flags={flags} saved={pg.saved || ""} savedBad={pg.bad} delivery={delivery}
      status={<span className="stat"><span className="dot" aria-hidden="true" />
        <svg className="tick" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9.5l4 4 8-9" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /></svg>
        <span className="bkr" hidden={!c.blockers}>{c.blockers} BLOCKER{c.blockers === 1 ? "" : "S"}</span><span className="cnt" role="status" aria-live="polite">{text}</span></span>}
      jump={<JumpBar open={openItems} goTo={goTo} />}
      pops={<>
        <OpenIds open={openItems} choicePage={choicePage} goTo={goTo} shown={popup === "ids"} onClose={() => setPopup("")} />
        <div className="rvpop menu" role="menu" hidden={popup !== "menu"}>
          <button className="all-yes" type="button" role="menuitem" onClick={() => markAll("yes", "Yes")}>Mark unanswered Yes</button>
          <button className="all-no" type="button" role="menuitem" onClick={() => markAll("no", "No")}>Mark unanswered No</button>
          <button className="copy" type="button" role="menuitem" onClick={() => void doCopy()}>Copy results</button>
          <button className="copy-blockers" type="button" role="menuitem" onClick={() => void copyBlockers()}>Copy blockers only</button>
          <button className="history" type="button" role="menuitem" disabled={!rows.length} onClick={() => { setPopup(""); const h = document.getElementById("rvhist") as HTMLDetailsElement; h.open = true; h.scrollIntoView({ behavior: "smooth", block: "start" }); }}>History</button>
          <button className="round-close" type="button" role="menuitem" disabled={!!sub} onClick={() => void roundClose()}>Save round now</button>
          <button className="clear" type="button" role="menuitem" disabled={!!sub} onClick={() => void clear()}>Clear my answers</button>
        </div></>}>
      {sends && !p.phases && <button className={"send-btn" + (c.allDone ? " ready" : "")} type="button" disabled={sendDone} onClick={() => void sendAll()}>{sendDone ? "Sent" : "Send to " + to}</button>}
      {p.deck && <button className="deck-btn" type="button" onClick={() => void deck()}>Build a deck</button>}
      <button className="copy" type="button" onClick={() => void doCopy()}>Copy results</button>
      <button className="clear" type="button" disabled={!!sub} onClick={() => void clear()}>Clear my answers</button>
      <button className="ids" type="button" aria-haspopup="dialog" aria-expanded={popup === "ids"} onClick={e => { e.stopPropagation(); setPopup(popup === "ids" ? "" : "ids"); }}
        title={choicePage ? "Items you haven't picked yet" : "Find and jump to an open item"}><span className="ids-l">{choicePage ? "Not picked" : "Open IDs"}</span> <span className="mono ids-n">({openItems.length.toLocaleString("en-US")})</span> ▴</button>
      <a className="back" hidden={!(c.allDone && folder)} href={folderUrl}>{"← Back to " + folderPages}</a>
      <span className="more"><button className="more-btn" type="button" aria-haspopup="menu" aria-expanded={popup === "menu"} onClick={e => { e.stopPropagation(); setPopup(popup === "menu" ? "" : "menu"); }}>More ▾</button></span>
    </Footer>);

  return <>
    <header className="top"><div className="wrap">{folder && <a className="crumb" href={folderUrl}>{"← " + folderPages}</a>}<h1>{p.title}</h1>{p.summary && <p dangerouslySetInnerHTML={{ __html: inline(p.summary) }} />}</div></header>
    <main className="wrap" id="page">
      {sub && <Held data={data} sub={sub} onUnlock={async () => { await postPage("/unlock", {}); await redraw(); }} />}
      {pageReplies.length > 0 && <section className="pthread" id="replies"><h2>Replies about this page</h2><Thread entries={pageReplies} label="Replies about this page" /></section>}
      {p.kind === "journey" && <Restart data={data} onRestart={async cp => { await flush(); await postPage("/restart", { checkpoint: cp, results: results() }); await redraw(); }} />}
      {hidden.size > 0 && <div className="rvdone">{hidden.size} approved and locked. They stay in Copy results.</div>}
      {body(renderItem)}
      {!reference && <History rows={rows} />}
    </main>
    {footer}
  </>;

  async function doCopy() {
    setPopup("");
    await copy();
    alert("Copied. Paste it into the " + (rel.split("/")[0] ?? "the").toUpperCase() + " session.");
    if (c?.allDone) returnSoon(flush);
  }
}

import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { fetchPage, rel, saveAnswers } from "@/lib/api";
import { toAnswer, toLocal } from "@/lib/model";
import type { Local, Locals, PageData } from "@/lib/types";

const POLL = 10000;
const SAVE_WAIT = 500;
const IDLE = 3000;

function typing(): boolean {
  const a = document.activeElement as HTMLInputElement | null;
  return !!a && (a.tagName === "TEXTAREA" || a.isContentEditable || (a.tagName === "INPUT" && !/^(radio|checkbox|button|submit|reset)$/i.test(a.type)));
}

export interface PageState {
  data: PageData | null;
  local: Locals;
  saved: string;
  bad: boolean;
  set: (id: string, next: Local) => void;
  flush: () => Promise<boolean>;
  redraw: () => Promise<void>;
  unsaved: () => boolean;
}

/** The page file, this tab's answers on top of it, saving, and the live redraw. */
export function usePage(): PageState {
  const [data, setData] = useState<PageData | null>(null);
  const [local, setLocal] = useState<Locals>({});
  const [saved, setSaved] = useState("");
  const [bad, setBad] = useState(false);
  const etag = useRef<string | null>(null);
  const dirty = useRef<Set<string>>(new Set());
  const now = useRef<Locals>({});
  const doc = useRef<PageData | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const lastAct = useRef(0);
  const busy = useRef(false);

  const take = useCallback((next: PageData, tag: string | null) => {
    etag.current = tag; doc.current = next;
    const fresh = toLocal(next);
    for (const id of dirty.current) fresh[id] = now.current[id];
    now.current = fresh;
    document.title = next.page.title;
    const ats = Object.values(next.page.rounds[next.page.rounds.length - 1].answers).map(a => a.at ?? "").filter(Boolean).sort();
    if (ats.length) setSaved(s => s || "Saved " + new Date(ats[ats.length - 1]).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }));
    setData(next); setLocal(fresh);
  }, []);

  const redraw = useCallback(async () => {
    const got = await fetchPage(null);
    if (got) take(got.data, got.etag);
  }, [take]);

  const poll = useCallback(async () => {
    if (dirty.current.size || typing() || Date.now() - lastAct.current < IDLE) return;
    const got = await fetchPage(etag.current);
    if (got) take(got.data, got.etag);
  }, [take]);

  const flush = useCallback(async (): Promise<boolean> => {
    window.clearTimeout(timer.current);
    while (busy.current) await new Promise(r => setTimeout(r, 50));
    const d = doc.current;
    if (!d) return true;
    const ids = [...dirty.current];
    const out: Record<string, { answer: string; note: string }> = {};
    for (const id of ids) {
      const a = toAnswer(d.page, id, now.current[id]);
      if ((a.answer === "changes" || a.answer === "risk") && !a.note.trim()) continue;
      out[id] = a;
    }
    if (!Object.keys(out).length) return true;
    const sent = { ...now.current };
    busy.current = true;
    try {
      await saveAnswers(d.page.rev, out);
      for (const id of Object.keys(out)) if (now.current[id] === sent[id]) dirty.current.delete(id);
      setSaved("Saved " + new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })); setBad(false);
      return true;
    } catch {
      setSaved("Not saved · retrying"); setBad(true);
      timer.current = window.setTimeout(() => void flush(), 2000);
      return false;
    } finally { busy.current = false; }
  }, []);

  const set = useCallback((id: string, next: Local) => {
    now.current = { ...now.current, [id]: next };
    dirty.current.add(id);
    flushSync(() => setLocal(now.current));
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), SAVE_WAIT);
  }, [flush]);

  useEffect(() => {
    void redraw().catch(() => setSaved("This page couldn't be loaded. It retries in a moment."));
    const t = window.setInterval(() => { if (!document.hidden) void poll().catch(() => undefined); }, POLL);
    const act = () => { lastAct.current = Date.now(); };
    for (const ev of ["input", "change", "keydown", "pointerdown", "click"]) document.addEventListener(ev, act, true);
    document.body.setAttribute("data-review-page", "/" + rel);
    return () => { window.clearInterval(t); for (const ev of ["input", "change", "keydown", "pointerdown", "click"]) document.removeEventListener(ev, act, true); };
  }, [redraw, poll]);

  return { data, local, saved, bad, set, flush, redraw, unsaved: () => dirty.current.size > 0 };
}

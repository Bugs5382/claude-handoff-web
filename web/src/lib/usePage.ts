import { useCallback, useEffect, useRef, useState } from "react";
import { fetchPage, postPage, rel, saveAnswers } from "@/lib/api";
import type { Local, PageData } from "@/lib/types";

const POLL = 10000;
const SAVE_WAIT = 500;

function localFrom(data: PageData): Record<string, Local> {
  const open = data.page.rounds[data.page.rounds.length - 1];
  const out: Record<string, Local> = {};
  for (const [id, st] of Object.entries(data.states)) {
    const a = open.answers[id];
    out[id] = { answer: st.reopened ? "" : st.answer, note: a && !st.reopened ? (a.note ?? "") : "" };
  }
  return out;
}

export interface PageState {
  data: PageData | null;
  local: Record<string, Local>;
  saved: string;
  setAnswer: (id: string, next: Local) => void;
  send: (results: string) => Promise<void>;
}

/** The page file, this tab's answers on top of it, saving and the live poll. */
export function usePage(): PageState {
  const [data, setData] = useState<PageData | null>(null);
  const [local, setLocal] = useState<Record<string, Local>>({});
  const [saved, setSaved] = useState("");
  const etag = useRef<string | null>(null);
  const dirty = useRef<Record<string, Local>>({});
  const timer = useRef<number | undefined>(undefined);
  const rev = useRef(0);

  const take = useCallback((next: PageData, tag: string | null) => {
    etag.current = tag; rev.current = next.page.rev;
    setData(next); setLocal({ ...localFrom(next), ...dirty.current });
  }, []);

  const refresh = useCallback(async () => {
    if (Object.keys(dirty.current).length) return;
    const got = await fetchPage(etag.current);
    if (got) take(got.data, got.etag);
  }, [take]);

  const flush = useCallback(async () => {
    window.clearTimeout(timer.current);
    const out = dirty.current;
    if (!Object.keys(out).length) return;
    try {
      await saveAnswers(rev.current, out);
      for (const id of Object.keys(out)) if (dirty.current[id] === out[id]) delete dirty.current[id];
      setSaved("Saved " + new Date().toTimeString().slice(0, 5));
    } catch {
      setSaved("Not saved · retrying");
      timer.current = window.setTimeout(() => void flush(), 2000);
    }
  }, []);

  const setAnswer = useCallback((id: string, next: Local) => {
    setLocal(l => ({ ...l, [id]: next }));
    if (next.answer === "changes" && !next.note.trim()) return;
    dirty.current = { ...dirty.current, [id]: next };
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), SAVE_WAIT);
  }, [flush]);

  const send = useCallback(async (results: string) => {
    await flush();
    await postPage("/send", { kind: "send", results });
    etag.current = null;
    await refresh();
  }, [flush, refresh]);

  useEffect(() => {
    void refresh().catch(() => setSaved("This page couldn't be loaded."));
    const t = window.setInterval(() => { if (!document.hidden) void refresh().catch(() => undefined); }, POLL);
    return () => window.clearInterval(t);
  }, [refresh]);

  useEffect(() => { document.body.setAttribute("data-review-page", "/" + rel); }, []);
  return { data, local, saved, setAnswer, send };
}

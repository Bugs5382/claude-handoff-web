import type { Local, PageData } from "@/lib/types";

export const rel = decodeURIComponent(location.pathname).replace(/^\/+|\/+$/g, "");
const API = "/_page/" + rel;

export async function fetchPage(etag: string | null): Promise<{ data: PageData; etag: string | null } | null> {
  const r = await fetch(API, { cache: "no-store", headers: etag ? { "If-None-Match": etag } : {} });
  if (r.status === 304) return null;
  if (!r.ok) throw new Error("GET " + r.status);
  return { data: (await r.json()) as PageData, etag: r.headers.get("ETag") };
}

export async function saveAnswers(base: number, answers: Record<string, Local>): Promise<void> {
  const r = await fetch(API + "/answers", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ base, answers }), cache: "no-store" });
  if (r.status !== 200) throw new Error("PUT " + r.status);
}

export async function postPage(path: string, body: unknown): Promise<Record<string, unknown>> {
  const r = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), cache: "no-store" });
  const out = (await r.json().catch(() => ({}))) as { errors?: string[]; error?: string };
  if (!r.ok) throw new Error((out.errors ?? [out.error ?? "HTTP " + r.status]).join("; "));
  return out;
}

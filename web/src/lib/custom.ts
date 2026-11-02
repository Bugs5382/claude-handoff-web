import type { ReactNode } from "react";
import type { ItemAction } from "@/elements/ItemMore";
import type { ItemDef, Locals, PageData } from "@/lib/types";

export interface TemplateProps {
  data: PageData;
  local: Locals;
  item: (it: ItemDef, n: number | string) => ReactNode;
  sendPhase: (id: string) => void;
  goTo: (id: string) => void;
}

/** Extra per-item actions, added by custom/custom.js. Each gets the item and returns an action, or null to skip it. */
export const itemActions: ((it: ItemDef, data: PageData) => ItemAction | null)[] = [];

/** Custom templates by name, added by custom/custom.js. */
export const templates: Record<string, (props: TemplateProps) => ReactNode> = {};

async function exists(url: string): Promise<boolean> {
  try { return (await fetch(url, { method: "HEAD", cache: "no-store" })).ok; } catch { return false; }
}

/** custom/ loads after the base and before the first page draws. A site without it loses nothing. */
export async function loadCustom(): Promise<void> {
  if (await exists("/custom/custom.css")) {
    const l = document.createElement("link"); l.rel = "stylesheet"; l.href = "/custom/custom.css"; document.head.appendChild(l);
  }
  if (await exists("/custom/custom.js")) {
    await new Promise<void>(done => {
      const s = document.createElement("script"); s.src = "/custom/custom.js";
      s.onload = () => done();
      s.onerror = () => { console.error("custom/custom.js didn't load"); done(); };
      document.body.appendChild(s);
    });
  }
}

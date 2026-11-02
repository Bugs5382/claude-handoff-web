import type { ItemDef, Local } from "@/lib/types";

/** What the bar counts: the same rules as rvCount in review.js. */
export function count(items: ItemDef[], local: Record<string, Local>, hidden: Set<string>) {
  const open = items.filter(it => !hidden.has(it.id));
  const answered = open.filter(it => { const l = local[it.id]; return !!l?.answer && (l.answer !== "changes" || !!l.note.trim()); });
  const yes = open.filter(it => local[it.id]?.answer === "yes");
  const total = open.length;
  const openIds = open.filter(it => !answered.includes(it)).map(it => it.id);
  return { total, answered: answered.length, openIds, hidden: items.length - open.length, allDone: total > 0 && answered.length === total, approved: total > 0 && yes.length === total };
}

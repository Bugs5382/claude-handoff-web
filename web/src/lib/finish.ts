import { folder, folderPages, folderUrl } from "@/lib/howto";

export function actToast(text: string, linkText: string): void {
  document.querySelectorAll(".site-toast.act").forEach(x => x.remove());
  const t = document.createElement("div"); t.className = "site-toast act"; t.setAttribute("role", "status");
  const sp = document.createElement("span"); sp.textContent = text; t.appendChild(sp);
  if (linkText && folder) { const a = document.createElement("a"); a.href = folderUrl; a.textContent = linkText; t.appendChild(a); }
  document.body.appendChild(t); requestAnimationFrame(() => t.classList.add("show"));
  setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 400); }, 4000);
}

let backTimer: number | null = null;

/** After Copy results on a finished page: back to the folder in 1.5 s unless the person moves or types. */
export function returnSoon(flush: () => Promise<boolean>): void {
  if (!folder || backTimer) return;
  let x0: number | null = null, y0 = 0;
  const stay = () => { if (backTimer) clearTimeout(backTimer); backTimer = null; off(); actToast("Staying on this page.", "← Back to " + folderPages); };
  const move = (e: Event) => { const m = e as PointerEvent; if (x0 === null) { x0 = m.clientX; y0 = m.clientY; return; } if (Math.abs(m.clientX - x0) + Math.abs(m.clientY - y0) > 12) stay(); };
  const evs: [string, (e: Event) => void][] = [["keydown", stay], ["wheel", stay], ["pointerdown", stay], ["touchstart", stay], ["pointermove", move]];
  const off = () => evs.forEach(([n, f]) => removeEventListener(n, f, true));
  evs.forEach(([n, f]) => addEventListener(n, f, true));
  actToast("Done. Back to " + folderPages + " in a moment · move or type to stay", "Go now");
  backTimer = window.setTimeout(async () => {
    off(); backTimer = null;
    const a = document.activeElement;
    if (a && (a.tagName === "TEXTAREA" || a.tagName === "INPUT")) return;
    if (!(await flush())) { actToast("Not saved yet, so staying here.", ""); return; }
    location.href = folderUrl;
  }, 1500);
}

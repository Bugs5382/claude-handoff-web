import { rel } from "@/lib/api";

const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);

/** An item's test steps in their own pop-out window, reused so it stays where it was put. */
export function openHowto(source: HTMLElement, id: string, title: string, build?: string | null): void {
  const w = window.open("about:blank", "howto", "width=520,height=720");
  if (!w) { alert("Allow pop-ups for this site to see the test steps."); return; }
  const d = w.document; d.open();
  const th = document.documentElement.getAttribute("data-theme");
  d.write(`<!doctype html><html lang="en"${th ? ` data-theme="${esc(th)}"` : ""}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<title>How to test: ${esc(id)}</title><link rel="stylesheet" href="${location.origin}/_site/site.css?v=37"></head>` +
    `<body class="site page howto-win"><p class="muted">How to test &middot; <code>${esc(id)}</code>${build ? ` &middot; Build under test: <code>${esc(build)}</code>` : ""}</p>` +
    `<h1>${esc(title)}</h1><div class="howto-body"></div><p class="muted">Answer on the main page.</p></body></html>`);
  d.close();
  (d.querySelector(".howto-body") as HTMLElement).innerHTML = source.innerHTML;
  d.querySelectorAll(".howto-body pre, .howto-body code.cmd").forEach(blk => {
    const b = d.createElement("button"); b.type = "button"; b.className = "copy-cmd"; b.textContent = "Copy";
    b.addEventListener("click", async () => {
      await w.navigator.clipboard.writeText((blk.textContent ?? "").trim());
      b.textContent = "Copied"; setTimeout(() => { b.textContent = "Copy"; }, 1500);
    });
    blk.insertAdjacentElement("afterend", b);
  });
  const links = (window as unknown as { siteLinks?: { hook: (doc: Document) => void } }).siteLinks;
  if (links) { (d as unknown as { siteLinks: boolean }).siteLinks = false; links.hook(d); }
  w.focus();
}

export const folder = rel.split("/")[0] ?? "";
export const folderUrl = "/" + folder + "/";
export const folderPages = (folder.length <= 3 ? folder.toUpperCase() : folder.slice(0, 1).toUpperCase() + folder.slice(1)) + " pages";

export const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

// Inline markup, escape first: **bold**, *em*, `code` and [text](url) with a plain http(s), relative or # link.
export function inline(s: unknown): string {
  return String(s ?? "").split(/(`[^`]*`)/).map(part => {
    if (/^`[^`]*`$/.test(part)) return "<code>" + esc(part.slice(1, -1)) + "</code>";
    let h = esc(part);
    h = h.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t: string, u: string) =>
      /^(https?:\/\/|\/|\.|#|[a-z0-9])/i.test(u) && !/^javascript:/i.test(u) ? `<a href="${u}">${t}</a>` : m);
    return h.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }).join("");
}

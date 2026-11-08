export const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

// Inline markup, escape first: **bold**, *em*, `code` and [text](url) with a plain http(s), relative or # link.
// With {copy: true} a code span, an http(s) link and a bare http(s) address are each followed by a small Copy
// button (class copy-inline, the text in data-copy); copyInline() in lib/copy.ts handles the click.
export interface InlineOpts { copy?: boolean }

const TOKEN = /\[([^\]]+)\]\(([^)\s]+)\)|https?:\/\/[^\s<>"]+/g;

// The clipboard-copy icon (lucide, 16px) and a check shown for a moment after a copy; both inherit the text colour.
const SVG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
const ICONS = SVG + ' class="ci-copy"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/><path d="M16 4h2a2 2 0 0 1 2 2v4"/><path d="M21 14H11"/><path d="m15 10-4 4 4 4"/></svg>'
  + SVG + ' class="ci-ok"><path d="M20 6 9 17l-5-5"/></svg>';

export function inline(s: unknown, o: InlineOpts = {}): string {
  const button = (v: string) => `<button type="button" class="copy-inline" data-copy="${esc(v)}" aria-label="Copy ${esc(v)}">${ICONS}</button>`;
  return String(s ?? "").split(/(`[^`]*`)/).map(part => {
    if (/^`[^`]*`$/.test(part)) {
      const c = part.slice(1, -1);
      return "<code>" + esc(c) + "</code>" + (o.copy && c ? button(c) : "");
    }
    // Buttons and bare addresses are held out of the emphasis pass so a * in an address is left alone.
    const held: string[] = [];
    const hold = (h: string) => "\u0001" + (held.push(h) - 1) + "\u0001";
    let out = "", at = 0;
    for (const m of part.replace(/\u0001/g, "").matchAll(TOKEN)) {
      out += esc(part.slice(at, m.index)); at = m.index + m[0].length;
      if (m[1] !== undefined) {
        const u = m[2] as string;
        if (/^(https?:\/\/|\/|\.|#|[a-z0-9])/i.test(u) && !/^javascript:/i.test(u)) {
          out += `<a href="${esc(u)}">${esc(m[1])}</a>`;
          if (o.copy && /^https?:\/\//i.test(u)) out += hold(button(u));
        } else out += esc(m[0]);
      } else if (o.copy) {
        const url = m[0].replace(/[.,;:!?)\]']+$/, "");
        out += hold(`<span class="copy-src">${esc(url)}</span>`) + hold(button(url)) + esc(m[0].slice(url.length));
      } else out += esc(m[0]);
    }
    out += esc(part.slice(at));
    return out.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\u0001(\d+)\u0001/g, (_, n: string) => held[Number(n)] as string);
  }).join("");
}

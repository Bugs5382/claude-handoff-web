export const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);

// Inline markup, escape first: **bold**, *em*, `code` and [text](url) with a plain http(s), relative or # link.
// With {copy: true} a code span, an http(s) link and a bare http(s) address are each followed by a small Copy
// button (class copy-inline, the text in data-copy); copyInline() in lib/copy.ts handles the click.
export interface InlineOpts { copy?: boolean }

const TOKEN = /\[([^\]]+)\]\(([^)\s]+)\)|https?:\/\/[^\s<>"]+/g;

export function inline(s: unknown, o: InlineOpts = {}): string {
  const button = (v: string) => `<button type="button" class="copy-cmd copy-inline" data-copy="${esc(v)}" aria-label="Copy ${esc(v)}">Copy</button>`;
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

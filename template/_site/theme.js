// Theme: Auto (follows the system's light or dark setting), Light or Dark, kept per browser in
// localStorage "site-theme". Load it in <head> right after site.css so data-theme is on <html> before
// the first paint (no flash):  <script src="/_site/theme.js?v=20"></script>
// review.js and live.js load it themselves on pages that don't, so the toggle shows up everywhere.
// The toggle (Auto / Light / Dark) goes in the page's header.top, or floats top-right without one.
(function () {
  if (window.siteTheme) { window.siteTheme.mount(); return; }
  const KEY = "site-theme", root = document.documentElement, CHOICES = [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]];
  function read() { try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" ? v : "auto"; } catch (e) { return "auto"; } }
  let cur = read();
  function apply() { if (cur === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", cur); }
  function paint() { document.querySelectorAll(".theme-tg button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.theme === cur))); }
  function set(v) {
    cur = v === "light" || v === "dark" ? v : "auto";
    try { if (cur === "auto") localStorage.removeItem(KEY); else localStorage.setItem(KEY, cur); } catch (e) { /* private window: this page only */ }
    apply(); paint();
  }
  function mount() {
    const b = document.body;
    if (!b || !b.classList.contains("site") || b.classList.contains("howto-win") || document.querySelector(".theme-tg")) return;
    const g = document.createElement("div"); g.className = "theme-tg"; g.setAttribute("role", "group"); g.setAttribute("aria-label", "Theme");
    for (const [v, l] of CHOICES) {
      const btn = document.createElement("button"); btn.type = "button"; btn.dataset.theme = v; btn.textContent = l;
      btn.title = v === "auto" ? "Follow the system setting" : l + " theme";
      btn.addEventListener("click", () => set(v));
      g.appendChild(btn);
    }
    const host = document.querySelector("header.top");
    if (host) host.appendChild(g); else { g.classList.add("floating"); b.appendChild(g); }
    paint();
  }
  apply();
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
  addEventListener("storage", e => { if (e.key === KEY) { cur = read(); apply(); paint(); } });
  window.siteTheme = { get: () => cur, set, mount };
})();

// A custom template: a round where each step can ask for an email draft, with a line of its own at the top.
// It runs as it stands, with no build. See _site/CUSTOM.md.
(function () {
  const { html, templates } = window.HandoffSite;
  templates["draft-round"] = ({ data, item }) => html`
    <p class="draft-intro">Each step here can have its own email. Press Draft email, say what you want, and read each version as it comes back.</p>
    ${data.page.items.map((it, i) => item(it, i + 1))}`;
})();

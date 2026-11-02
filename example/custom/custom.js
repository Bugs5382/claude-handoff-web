// A custom template: a round where each step can ask for an email draft, with a line of its own at the top.
// It runs as it stands, with no build. See _site/CUSTOM.md.
(function () {
  const { html, templates, itemActions, tours } = window.HandoffSite;
  tours["draft-round"] = [
    { element: ".draft-intro", title: "A custom page", text: "This page comes from custom/, and uses the site's own elements." },
    { element: ".item-more-btn", title: "Generate an email", text: "Press More on a step, then say what the email should do and how it should sound." },
    { element: ".email", title: "Versions", text: "Each email that comes back is a new version here, with what you asked for." },
  ];
  itemActions.push(it => ({ name: "copy-title", label: "Copy this step's title", onSelect: () => navigator.clipboard.writeText(it.title) }));
  templates["draft-round"] = ({ data, item }) => html`
    <p class="draft-intro">Each step here can have its own email. Press More, then Generate an email, say what you want, and read each version as it comes back.</p>
    ${data.page.items.map((it, i) => item(it, i + 1))}`;
})();

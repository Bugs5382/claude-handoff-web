// A custom template: a round with a progress line of its own at the top, plus one per-item action and a tour.
// It runs as it stands, with no build. See _site/CUSTOM.md.
(function () {
  const { html, templates, itemActions, pageActions, tours } = window.HandoffSite;
  pageActions.push(() => ({ name: "guide", label: "Open the guide", href: "/guide/" }));
  tours["progress-round"] = [
    { element: ".custom-progress", title: "A custom page", text: "This line comes from custom/, and the cards below are the site's own elements." },
    { element: ".item-more-btn", title: "Custom actions", text: "An action from custom/ joins the item's More button." },
  ];
  itemActions.push(it => ({ name: "copy-title", label: "Copy this step's title", onSelect: () => navigator.clipboard.writeText(it.title) }));
  templates["progress-round"] = ({ data, local, item }) => {
    const done = data.page.items.filter(it => local[it.id] && local[it.id].v).length;
    return html`
      <p class="custom-progress">${done} of ${data.page.items.length} done on this page.</p>
      ${data.page.items.map((it, i) => item(it, i + 1))}`;
  };
})();

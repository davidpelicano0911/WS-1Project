(() => {
  const root = document.querySelector(".player-detail-tabs-shell");
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll("[data-player-tab]"));
  const panels = Array.from(root.querySelectorAll(".player-detail-tab-panel"));
  const rdfSection = root.querySelector("[data-player-rdf-panel]");
  let rdfLoaded = false;
  let rdfLoading = false;

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const renderRdfTriples = async () => {
    if (!rdfSection || rdfLoaded || rdfLoading) {
      return;
    }

    const endpoint = rdfSection.dataset.rdfUrl;
    const loading = rdfSection.querySelector("[data-rdf-loading]");
    const table = rdfSection.querySelector("[data-rdf-table]");
    const body = rdfSection.querySelector("[data-rdf-body]");
    const empty = rdfSection.querySelector("[data-rdf-empty]");
    const error = rdfSection.querySelector("[data-rdf-error]");
    const errorText = rdfSection.querySelector("[data-rdf-error-text]");
    const countWrap = rdfSection.querySelector("[data-rdf-count-wrap]");
    const count = rdfSection.querySelector("[data-rdf-count]");

    if (!endpoint || !loading || !table || !body || !empty || !error || !errorText || !countWrap || !count) {
      return;
    }

    rdfLoading = true;
    loading.hidden = false;
    table.hidden = true;
    empty.hidden = true;
    error.hidden = true;
    countWrap.hidden = true;

    try {
      const response = await fetch(endpoint, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || "The RDF data could not be loaded right now.");
      }

      const triples = Array.isArray(payload.triples) ? payload.triples : [];
      if (!triples.length) {
        empty.hidden = false;
        rdfLoaded = true;
        return;
      }

      body.innerHTML = triples
        .map(
          (triple) => `
            <tr>
              <td style="padding-left: 1rem; vertical-align: middle;">
                <span style="
                    display: inline-block;
                    background: rgba(251,191,36,0.1);
                    border: 1px solid rgba(251,191,36,0.2);
                    color: #fbbf24;
                    font-family: monospace;
                    font-size: 0.8rem;
                    padding: 2px 8px;
                    border-radius: 4px;
                    white-space: nowrap;
                ">${escapeHtml(triple.predicate)}</span>
              </td>
              <td class="text-break" style="padding-left: 1rem; color: var(--text-primary, #e2e8f0);">
                ${escapeHtml(triple.value)}
              </td>
            </tr>
          `
        )
        .join("");

      count.textContent = `${triples.length} triple${triples.length === 1 ? "" : "s"}`;
      countWrap.hidden = false;
      table.hidden = false;
      rdfLoaded = true;
    } catch (fetchError) {
      errorText.textContent = fetchError instanceof Error
        ? fetchError.message
        : "The RDF data could not be loaded right now.";
      error.hidden = false;
    } finally {
      loading.hidden = true;
      rdfLoading = false;
    }
  };

  const activateTab = (tabName, updateHash = true) => {
    const targetButton = buttons.find((button) => button.dataset.playerTab === tabName) || buttons[0];
    if (!targetButton) return;

    buttons.forEach((button) => {
      const isActive = button === targetButton;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", isActive ? "true" : "false");
      button.tabIndex = isActive ? 0 : -1;
    });

    panels.forEach((panel) => {
      const isActive = panel.id === `player-tab-${targetButton.dataset.playerTab}`;
      panel.classList.toggle("active", isActive);
      panel.hidden = !isActive;
    });

    if (updateHash) {
      history.replaceState(null, "", `#${targetButton.dataset.playerTab}`);
    }

    document.dispatchEvent(
      new CustomEvent("player-detail-tab:change", {
        detail: { tab: targetButton.dataset.playerTab },
      })
    );

    if (targetButton.dataset.playerTab === "rdf") {
      renderRdfTriples();
    }
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.playerTab));
  });

  const hash = window.location.hash.replace("#", "").trim();
  activateTab(hash || buttons[0]?.dataset.playerTab || "overview", false);
})();

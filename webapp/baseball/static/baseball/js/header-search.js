(() => {
  const root = document.querySelector(".portal-search");
  if (!root) return;

  const toggle = root.querySelector(".js-portal-search-toggle");
  const panel = root.querySelector(".portal-search-panel");
  const input = root.querySelector(".portal-search-input");
  const playersList = root.querySelector('[data-search-section="players"]');
  const teamsList = root.querySelector('[data-search-section="teams"]');
  const searchUrl = root.dataset.searchUrl;
  const playersUrl = root.dataset.playersUrl;

  let debounceTimer = null;
  let activeRequest = 0;

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const renderEmpty = (container, text) => {
    container.innerHTML = `<div class="portal-search-empty">${text}</div>`;
  };

  const renderSection = (container, items, emptyText) => {
    if (!items.length) {
      renderEmpty(container, emptyText);
      return;
    }
    container.innerHTML = items
      .map(
        (item) => `
          <a class="portal-search-result" href="${escapeHtml(item.url)}">
            <div>
              <div class="portal-search-result-label">${escapeHtml(item.label)}</div>
              <div class="portal-search-result-meta">${escapeHtml(item.meta || "")}</div>
            </div>
            <span class="portal-search-result-kind">${escapeHtml(item.kind)}</span>
          </a>
        `
      )
      .join("");
  };

  const setOpen = (open) => {
    root.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    panel.hidden = false;
    if (open) {
      requestAnimationFrame(() => input.focus());
      if (!input.value.trim()) {
        renderEmpty(playersList, "Search by name to find player dossiers.");
        renderEmpty(teamsList, "Search by club, franchise or park.");
      }
    }
  };

  const close = () => {
    root.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
  };

  const fetchResults = async (query) => {
    const requestId = ++activeRequest;
    if (query.length < 2) {
      renderEmpty(playersList, "Type at least 2 characters.");
      renderEmpty(teamsList, "Type at least 2 characters.");
      return;
    }

    renderEmpty(playersList, "Searching players...");
    renderEmpty(teamsList, "Searching teams...");

    try {
      const response = await fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok || requestId !== activeRequest) return;
      const payload = await response.json();
      if (requestId !== activeRequest) return;
      renderSection(playersList, payload.players || [], "No player matches found.");
      renderSection(teamsList, payload.teams || [], "No team matches found.");
    } catch (error) {
      renderEmpty(playersList, "Search is unavailable right now.");
      renderEmpty(teamsList, "Search is unavailable right now.");
    }
  };

  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    const isOpen = root.classList.contains("is-open");
    if (isOpen) {
      close();
    } else {
      setOpen(true);
    }
  });

  input.addEventListener("input", () => {
    const query = input.value.trim();
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => fetchResults(query), 180);
  });

  root.querySelector(".portal-search-form").addEventListener("submit", (event) => {
    const query = input.value.trim();
    if (!query) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    window.location.href = `${playersUrl}?q=${encodeURIComponent(query)}`;
  });

  document.addEventListener("click", (event) => {
    if (!root.contains(event.target)) {
      close();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      close();
    }
  });
})();

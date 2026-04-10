document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-player-catalog-form]");
  const shell = document.getElementById("players-catalog-shell");
  if (!form || !shell) {
    return;
  }

  const totalNodes = Array.from(document.querySelectorAll(".js-player-total-count"));
  const filterCountNodes = Array.from(document.querySelectorAll(".js-player-active-filter-count"));
  const catalogCopyNode = document.querySelector(".js-player-catalog-copy");
  let controller = null;
  let debounceTimer = null;
  let latestRequestId = 0;

  const setLoading = (loading) => {
    shell.classList.toggle("is-loading", loading);
    shell.setAttribute("aria-busy", loading ? "true" : "false");
    if (window.BaseBallXLoading) {
      if (loading) {
        window.BaseBallXLoading.show();
      } else {
        window.BaseBallXLoading.hide();
      }
    }
  };

  const updateSummary = (fragment) => {
    const total = Number(fragment.dataset.totalPlayers || 0);
    const activeFilterCount = Number(fragment.dataset.activeFiltersCount || 0);
    const hasActiveFilters = fragment.dataset.hasActiveFilters === "1";

    totalNodes.forEach((node) => {
      node.textContent = String(total);
    });
    filterCountNodes.forEach((node) => {
      node.textContent = String(activeFilterCount);
    });
    if (catalogCopyNode) {
      catalogCopyNode.textContent = hasActiveFilters
        ? `${total} players matching the current filter stack.`
        : `${total} players in the current catalog view.`;
    }
  };

  const buildUrl = (page = null) => {
    const params = new URLSearchParams(new FormData(form));
    params.delete("page");
    if (page) {
      params.set("page", String(page));
    }
    params.set("fragment", "catalog");
    return `${form.action}?${params.toString()}`;
  };

  const buildHistoryUrl = (page = null) => {
    const params = new URLSearchParams(new FormData(form));
    params.delete("page");
    if (page) {
      params.set("page", String(page));
    }
    const query = params.toString();
    return query ? `${form.action}?${query}` : form.action;
  };

  const syncFormWithUrl = (url) => {
    const parsed = new URL(url, window.location.origin);
    const params = parsed.searchParams;
    form.querySelectorAll("input, select").forEach((field) => {
      if (!field.name) {
        return;
      }
      if (field instanceof HTMLInputElement && field.type === "checkbox") {
        field.checked = params.get(field.name) === field.value;
        return;
      }
      const nextValue = params.get(field.name);
      field.value = nextValue === null ? "" : nextValue;
    });
  };

  const loadCatalog = async (url, pushState = true) => {
    if (controller) {
      controller.abort();
    }
    const requestId = ++latestRequestId;
    controller = new AbortController();
    setLoading(true);

    try {
      const response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error("Failed to load players.");
      }
      const html = await response.text();
      if (requestId !== latestRequestId) {
        return;
      }
      shell.innerHTML = html;
      const fragment = shell.querySelector(".player-catalog-fragment");
      if (fragment) {
        updateSummary(fragment);
      }
      if (typeof window.initPlayerCardPhotos === "function") {
        window.initPlayerCardPhotos(shell);
      }
      if (pushState) {
        window.history.pushState({}, "", buildHistoryUrl(new URL(url, window.location.origin).searchParams.get("page")));
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        shell.innerHTML = `
          <div class="empty-state">
            <i class="bi bi-exclamation-circle-fill"></i>
            Could not load the player catalog.
          </div>
        `;
      }
    } finally {
      if (requestId === latestRequestId) {
        setLoading(false);
      }
    }
  };

  const scheduleTextLoad = () => {
    window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      loadCatalog(buildUrl(), true);
    }, 280);
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    window.clearTimeout(debounceTimer);
    loadCatalog(buildUrl(), true);
  });

  form.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement)) {
      return;
    }

    if (target.type === "text" || target.type === "search") {
      scheduleTextLoad();
      return;
    }

    if (target.type === "checkbox") {
      window.clearTimeout(debounceTimer);
      loadCatalog(buildUrl(), true);
    }
  });

  form.addEventListener("change", (event) => {
    const target = event.target;
    if (
      target instanceof HTMLSelectElement ||
      (target instanceof HTMLInputElement && (target.type === "radio" || target.type === "checkbox"))
    ) {
      window.clearTimeout(debounceTimer);
      loadCatalog(buildUrl(), true);
    }
  });

  shell.addEventListener("click", (event) => {
    const link = event.target.closest(".pager-app a");
    if (!link) {
      return;
    }
    event.preventDefault();
    const url = new URL(link.href, window.location.origin);
    const page = url.searchParams.get("page");
    loadCatalog(buildUrl(page), true);
  });

  window.addEventListener("popstate", () => {
    window.clearTimeout(debounceTimer);
    syncFormWithUrl(window.location.href);
    const url = new URL(window.location.href);
    const page = url.searchParams.get("page");
    loadCatalog(buildUrl(page), false);
  });

  syncFormWithUrl(window.location.href);
  loadCatalog(buildUrl(new URL(window.location.href).searchParams.get("page")), false);
});

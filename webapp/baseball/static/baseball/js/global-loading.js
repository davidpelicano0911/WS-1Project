(() => {
  const overlay = document.querySelector("[data-site-loading-overlay]");
  if (!overlay) {
    return;
  }

  let visibleCount = 1;

  const show = () => {
    visibleCount += 1;
    overlay.classList.add("is-visible");
  };

  const hide = () => {
    visibleCount = Math.max(0, visibleCount - 1);
    if (visibleCount === 0) {
      overlay.classList.remove("is-visible");
    }
  };

  const forceHide = () => {
    visibleCount = 0;
    overlay.classList.remove("is-visible");
  };

  const isSamePageHashLink = (url) =>
    url.origin === window.location.origin &&
    url.pathname === window.location.pathname &&
    url.search === window.location.search &&
    url.hash;

  window.BaseBallXLoading = { show, hide, forceHide };

  window.addEventListener("load", () => {
    window.setTimeout(forceHide, 120);
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link) {
      return;
    }

    if (
      link.hasAttribute("download") ||
      link.target === "_blank" ||
      link.dataset.noGlobalLoading !== undefined ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }

    const href = (link.getAttribute("href") || "").trim();
    if (!href || href.startsWith("#") || href.startsWith("javascript:") || href.startsWith("mailto:") || href.startsWith("tel:")) {
      return;
    }

    const url = new URL(href, window.location.href);
    if (isSamePageHashLink(url)) {
      return;
    }

    show();
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (form.dataset.noGlobalLoading !== undefined) {
      return;
    }
    show();
  });

  window.addEventListener("pageshow", () => {
    forceHide();
  });
})();

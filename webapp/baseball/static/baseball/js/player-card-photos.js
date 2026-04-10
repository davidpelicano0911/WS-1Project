(() => {
  const processedCards = new WeakSet();

  const handleImageFailure = (card, img, photoOnlyMode) => {
    const fallback = (img.dataset.fallback || "").trim();
    if (fallback && img.src !== fallback) {
      img.src = fallback;
      return;
    }

    const defaultImage = (img.dataset.default || "").trim();
    if (defaultImage && img.src !== defaultImage) {
      if (photoOnlyMode) {
        card.style.display = "none";
        return;
      }
      img.src = defaultImage;
      return;
    }

    if (photoOnlyMode) {
      card.style.display = "none";
      return;
    }

    img.style.display = "none";
  };

  const initPlayerCardPhotos = (root = document) => {
    const grids = root.matches?.(".player-card-grid")
      ? [root]
      : Array.from(root.querySelectorAll?.(".player-card-grid") || []);

    grids.forEach((grid) => {
      const fragment = grid.closest(".player-catalog-fragment");
      const photoOnlyMode = fragment?.dataset.photoOnly === "1";

      grid.querySelectorAll(".player-card-entry").forEach((card) => {
        if (processedCards.has(card)) {
          return;
        }
        processedCards.add(card);

        const img = card.querySelector(".player-card-photo");
        if (!img) {
          return;
        }

        img.addEventListener("error", () => handleImageFailure(card, img, photoOnlyMode));

        if (img.complete && (!img.naturalWidth || !img.naturalHeight)) {
          handleImageFailure(card, img, photoOnlyMode);
        }
      });
    });
  };

  window.initPlayerCardPhotos = initPlayerCardPhotos;
  document.addEventListener("DOMContentLoaded", () => initPlayerCardPhotos(document));
})();

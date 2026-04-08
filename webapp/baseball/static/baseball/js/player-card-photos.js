document.addEventListener("DOMContentLoaded", () => {
  const grid = document.querySelector(".player-card-grid");
  if (!grid) {
    return;
  }

  const photoFilterActive = grid.dataset.photoFilterActive === "1";

  const hideCard = (card) => {
    if (!card || !photoFilterActive) {
      return;
    }
    card.hidden = true;
  };

  const handleImageFailure = (img) => {
    const fallback = (img.dataset.fallback || "").trim();
    if (fallback && img.src !== fallback) {
      img.src = fallback;
      return;
    }

    img.style.display = "none";
    hideCard(img.closest(".player-card-entry"));
  };

  grid.querySelectorAll(".player-card-entry").forEach((card) => {
    const img = card.querySelector(".player-card-photo");
    if (!img) {
      hideCard(card);
      return;
    }

    img.addEventListener("error", () => handleImageFailure(img));

    if (img.complete && (!img.naturalWidth || !img.naturalHeight)) {
      handleImageFailure(img);
    }
  });
});

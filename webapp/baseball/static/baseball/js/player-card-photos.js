document.addEventListener("DOMContentLoaded", () => {
  const grid = document.querySelector(".player-card-grid");
  if (!grid) {
    return;
  }

  const handleImageFailure = (img) => {
    const fallback = (img.dataset.fallback || "").trim();
    if (fallback && img.src !== fallback) {
      img.src = fallback;
      return;
    }

    img.style.display = "none";
  };

  grid.querySelectorAll(".player-card-entry").forEach((card) => {
    const img = card.querySelector(".player-card-photo");
    if (!img) {
      return;
    }

    img.addEventListener("error", () => handleImageFailure(img));

    if (img.complete && (!img.naturalWidth || !img.naturalHeight)) {
      handleImageFailure(img);
    }
  });
});

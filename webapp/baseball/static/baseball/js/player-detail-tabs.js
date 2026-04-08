(() => {
  const root = document.querySelector(".player-detail-tabs-shell");
  if (!root) return;

  const buttons = Array.from(root.querySelectorAll("[data-player-tab]"));
  const panels = Array.from(root.querySelectorAll(".player-detail-tab-panel"));

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
  };

  buttons.forEach((button) => {
    button.addEventListener("click", () => activateTab(button.dataset.playerTab));
  });

  const hash = window.location.hash.replace("#", "").trim();
  activateTab(hash || buttons[0]?.dataset.playerTab || "overview", false);
})();

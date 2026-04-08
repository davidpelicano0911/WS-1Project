(function () {
    const endpoint = document.body?.dataset.compareSelectionUrl;
    if (!endpoint) {
        return;
    }

    const buttons = () => Array.from(document.querySelectorAll("[data-compare-select]"));
    const modalBackdrop = document.querySelector("[data-compare-modal-backdrop]");
    const modalMessage = document.querySelector("[data-compare-modal-message]");

    const getCookie = (name) => {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) {
            return parts.pop().split(";").shift();
        }
        return "";
    };

    const showModal = (message) => {
        if (!modalBackdrop || !modalMessage) {
            return;
        }
        modalMessage.textContent = message;
        modalBackdrop.hidden = false;
        document.body.classList.add("compare-modal-open");
    };

    const hideModal = () => {
        if (!modalBackdrop) {
            return;
        }
        modalBackdrop.hidden = true;
        document.body.classList.remove("compare-modal-open");
    };

    const selectionContains = (selection, button) => {
        if (!selection || selection.type !== button.dataset.compareType) {
            return false;
        }
        return (selection.items || []).some((item) => item.id === button.dataset.compareId);
    };

    const updateButtonState = (button, selection) => {
        const active = selectionContains(selection, button);
        const label = button.querySelector("[data-compare-select-label]");
        const icon = button.querySelector("i");

        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");

        if (label) {
            label.textContent = active ? "Selected" : "Compare";
        }

        if (icon) {
            icon.className = active ? "bi bi-check2-circle" : "bi bi-plus-circle";
        }
    };

    const updateAllButtons = (selection) => {
        buttons().forEach((button) => updateButtonState(button, selection));
    };

    const sendSelectionRequest = async (button) => {
        const payload = {
            action: button.dataset.compareAction || "toggle",
            item_type: button.dataset.compareType,
            item_id: button.dataset.compareId,
            label: button.dataset.compareLabel || "",
            year: button.dataset.compareYear || "",
        };

        const response = await fetch(endpoint, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok || !data.ok) {
            showModal(data.message || "The comparison selection could not be updated.");
            if (data.selection) {
                updateAllButtons(data.selection);
            }
            return;
        }

        updateAllButtons(data.selection);
        if (button.dataset.compareReloadOnSuccess === "1") {
            window.location.reload();
        }
    };

    document.addEventListener("click", (event) => {
        const trigger = event.target.closest("[data-compare-select], [data-compare-action]");
        if (!trigger) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        sendSelectionRequest(trigger).catch(() => {
            showModal("The comparison selection could not be updated right now.");
        });
    });

    document.querySelectorAll("[data-compare-modal-close]").forEach((button) => {
        button.addEventListener("click", hideModal);
    });

    if (modalBackdrop) {
        modalBackdrop.addEventListener("click", (event) => {
            if (event.target === modalBackdrop) {
                hideModal();
            }
        });
    }

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            hideModal();
        }
    });
})();

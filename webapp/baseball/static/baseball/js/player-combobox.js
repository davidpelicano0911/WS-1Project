(function () {
    const normalize = (value) => value.trim().toLowerCase();

    document.querySelectorAll("[data-combobox]").forEach((combobox) => {
        const form = combobox.closest("form");
        const hiddenInput = combobox.querySelector('input[type="hidden"]');
        const textInput = combobox.querySelector("[data-combobox-input]");
        const toggleButton = combobox.querySelector("[data-combobox-toggle]");
        const menu = combobox.querySelector("[data-combobox-menu]");
        const emptyState = combobox.querySelector("[data-combobox-empty]");
        const optionButtons = Array.from(combobox.querySelectorAll(".combobox-option"));
        const selectableOptions = optionButtons.filter((button) => button.dataset.reset !== "true");
        let selectedLabel = textInput.value.trim();

        if (!hiddenInput || !textInput || !menu || !toggleButton || !form) {
            return;
        }

        const setExpanded = (expanded) => {
            combobox.classList.toggle("open", expanded);
            textInput.setAttribute("aria-expanded", expanded ? "true" : "false");
            menu.hidden = !expanded;
        };

        const syncActiveOption = () => {
            optionButtons.forEach((button) => {
                const isActive = button.dataset.value === hiddenInput.value;
                button.classList.toggle("active", isActive);
                if (button.hasAttribute("aria-selected")) {
                    button.setAttribute("aria-selected", isActive ? "true" : "false");
                }
            });
        };

        const syncDisplayToSelection = () => {
            textInput.value = hiddenInput.value ? selectedLabel : "";
        };

        const filterOptions = (query) => {
            const searchTerm = normalize(query);
            let visibleCount = 0;

            optionButtons.forEach((button) => {
                if (button.dataset.reset === "true") {
                    button.hidden = searchTerm.length > 0;
                    return;
                }

                const matches = !searchTerm || normalize(button.dataset.label).includes(searchTerm);
                button.hidden = !matches;
                if (matches) {
                    visibleCount += 1;
                }
            });

            if (emptyState) {
                emptyState.hidden = visibleCount > 0 || selectableOptions.length === 0;
            }
        };

        const openMenu = () => {
            setExpanded(true);
            filterOptions(textInput.value === selectedLabel ? "" : textInput.value);
        };

        const closeMenu = ({ restoreSelection = false } = {}) => {
            if (restoreSelection) {
                syncDisplayToSelection();
            }
            setExpanded(false);
            filterOptions("");
        };

        const selectOption = (button) => {
            hiddenInput.value = button.dataset.value || "";
            selectedLabel = button.dataset.label || "";
            syncActiveOption();
            syncDisplayToSelection();
            closeMenu();
            form.submit();
        };

        textInput.addEventListener("focus", openMenu);

        textInput.addEventListener("input", () => {
            if (textInput.value.trim() !== selectedLabel) {
                hiddenInput.value = "";
                syncActiveOption();
            }
            openMenu();
        });

        textInput.addEventListener("keydown", (event) => {
            const visibleOptions = optionButtons.filter((button) => !button.hidden);
            const visibleSelectableOptions = selectableOptions.filter((button) => !button.hidden);

            if (event.key === "Escape") {
                event.preventDefault();
                closeMenu({ restoreSelection: true });
                textInput.blur();
                return;
            }

            if (event.key === "Enter") {
                event.preventDefault();
                if (visibleSelectableOptions[0] || visibleOptions[0]) {
                    selectOption(visibleSelectableOptions[0] || visibleOptions[0]);
                }
                return;
            }

            if (event.key === "ArrowDown" && (visibleSelectableOptions[0] || visibleOptions[0])) {
                event.preventDefault();
                openMenu();
                (visibleSelectableOptions[0] || visibleOptions[0]).focus();
            }
        });

        toggleButton.addEventListener("click", () => {
            if (menu.hidden) {
                openMenu();
                textInput.focus({ preventScroll: true });
                return;
            }
            closeMenu({ restoreSelection: true });
        });

        optionButtons.forEach((button) => {
            button.addEventListener("click", () => {
                selectOption(button);
            });

            button.addEventListener("keydown", (event) => {
                const visibleOptions = optionButtons.filter((option) => !option.hidden);
                const currentIndex = visibleOptions.indexOf(button);

                if (event.key === "ArrowDown" && currentIndex < visibleOptions.length - 1) {
                    event.preventDefault();
                    visibleOptions[currentIndex + 1].focus();
                }

                if (event.key === "ArrowUp") {
                    event.preventDefault();
                    if (currentIndex > 0) {
                        visibleOptions[currentIndex - 1].focus();
                    } else {
                        textInput.focus();
                    }
                }

                if (event.key === "Escape") {
                    event.preventDefault();
                    closeMenu({ restoreSelection: true });
                    textInput.focus();
                }
            });
        });

        document.addEventListener("mousedown", (event) => {
            if (!combobox.contains(event.target)) {
                closeMenu({ restoreSelection: true });
            }
        });

        syncActiveOption();
        filterOptions("");
    });
}());

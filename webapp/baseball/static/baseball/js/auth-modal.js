(function () {
    const backdrop = document.querySelector("[data-auth-modal-backdrop]");
    if (!backdrop) {
        return;
    }

    const card = backdrop.querySelector(".auth-modal-card");
    const openers = Array.from(document.querySelectorAll("[data-auth-modal-open]"));
    const closeButtons = Array.from(document.querySelectorAll("[data-auth-modal-close]"));
    const tabButtons = Array.from(document.querySelectorAll("[data-auth-tab-trigger]"));
    const forms = {
        login: backdrop.querySelector('[data-auth-form="login"]'),
        register: backdrop.querySelector('[data-auth-form="register"]'),
    };
    const errorBlocks = {
        login: backdrop.querySelector('[data-auth-errors="login"]'),
        register: backdrop.querySelector('[data-auth-errors="register"]'),
    };

    let activeTab = "login";
    let busy = false;

    function animateCardResize(mutator) {
        if (!card) {
            mutator();
            return;
        }

        const startHeight = card.getBoundingClientRect().height;
        mutator();
        const endHeight = card.scrollHeight;

        if (Math.abs(startHeight - endHeight) < 2) {
            return;
        }

        card.style.height = `${startHeight}px`;
        card.classList.add("is-resizing");
        card.getBoundingClientRect();
        requestAnimationFrame(() => {
            card.style.height = `${endHeight}px`;
        });

        const cleanup = () => {
            card.style.height = "";
            card.classList.remove("is-resizing");
            card.removeEventListener("transitionend", cleanup);
        };

        card.addEventListener("transitionend", cleanup);
    }

    function fieldErrorNode(tab, fieldName) {
        return backdrop.querySelector(`[data-auth-field-error="${tab}-${fieldName}"]`);
    }

    function clearErrors(tab) {
        if (errorBlocks[tab]) {
            errorBlocks[tab].hidden = true;
            errorBlocks[tab].innerHTML = "";
        }
        forms[tab].querySelectorAll("[data-auth-field-error]").forEach((node) => {
            node.hidden = true;
            node.textContent = "";
        });
        ["username", "password", "email", "password1", "password2"].forEach((fieldName) => {
            const node = fieldErrorNode(tab, fieldName);
            if (node) {
                node.hidden = true;
                node.textContent = "";
            }
        });
    }

    function clearAllErrors() {
        clearErrors("login");
        clearErrors("register");
    }

    function setTab(tab, { animate = true } = {}) {
        const applyTabState = () => {
            activeTab = tab;
            tabButtons.forEach((button) => {
                button.classList.toggle("is-active", button.dataset.authTabTrigger === tab);
            });
            Object.entries(forms).forEach(([name, form]) => {
                const isActive = name === tab;
                form.hidden = !isActive;
                form.classList.toggle("is-active", isActive);
            });
            clearErrors(tab);
        };

        if (!animate || backdrop.hidden) {
            applyTabState();
            return;
        }

        animateCardResize(applyTabState);
    }

    function openModal(tab) {
        setTab(tab || activeTab, { animate: false });
        backdrop.hidden = false;
        document.body.classList.add("auth-modal-open");
    }

    function closeModal() {
        if (busy) {
            return;
        }
        backdrop.hidden = true;
        document.body.classList.remove("auth-modal-open");
        clearAllErrors();
    }

    function getCookie(name) {
        const cookies = document.cookie ? document.cookie.split(";") : [];
        for (const cookie of cookies) {
            const trimmed = cookie.trim();
            if (trimmed.startsWith(`${name}=`)) {
                return decodeURIComponent(trimmed.slice(name.length + 1));
            }
        }
        return "";
    }

    function setBusy(nextBusy) {
        busy = nextBusy;
        Object.values(forms).forEach((form) => {
            Array.from(form.elements).forEach((element) => {
                element.disabled = nextBusy;
            });
        });
        tabButtons.forEach((button) => {
            button.disabled = nextBusy;
        });
    }

    function renderErrors(tab, errors) {
        clearErrors(tab);
        if (!errors) {
            return;
        }

        if (errors.non_field_errors && errors.non_field_errors.length && errorBlocks[tab]) {
            errorBlocks[tab].hidden = false;
            errorBlocks[tab].innerHTML = errors.non_field_errors.map((error) => `<div>${error}</div>`).join("");
        }

        Object.entries(errors.field_errors || {}).forEach(([fieldName, messages]) => {
            if (fieldName === "__all__" && errorBlocks[tab]) {
                errorBlocks[tab].hidden = false;
                errorBlocks[tab].innerHTML = messages.map((error) => `<div>${error}</div>`).join("");
                return;
            }
            const node = fieldErrorNode(tab, fieldName);
            if (node) {
                node.hidden = false;
                node.textContent = messages.join(", ");
            }
        });
    }

    async function submitForm(form, tab) {
        clearErrors(tab);
        const formData = new FormData(form);
        setBusy(true);

        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": getCookie("csrftoken"),
                    Accept: "application/json",
                },
                body: formData,
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                if (payload.tab) {
                    setTab(payload.tab);
                }
                renderErrors(payload.tab || tab, payload.errors || {});
                return;
            }
            window.location.assign(payload.redirect_url || window.location.href);
        } catch (error) {
            renderErrors(tab, { non_field_errors: ["Something went wrong. Try again."], field_errors: {} });
        } finally {
            setBusy(false);
        }
    }

    openers.forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            openModal(link.dataset.authModalOpen || "login");
        });
    });

    tabButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (!busy) {
                setTab(button.dataset.authTabTrigger);
            }
        });
    });

    Object.entries(forms).forEach(([tab, form]) => {
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            submitForm(form, tab);
        });
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    backdrop.addEventListener("click", (event) => {
        if (event.target === backdrop) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && !backdrop.hidden) {
            closeModal();
        }
    });

    setTab(activeTab, { animate: false });
})();

(function () {
    const root = document.querySelector("[data-entity-edit-app]");
    const stateElement = document.getElementById("entity-edit-state");

    if (!root || !stateElement) {
        return;
    }

    let editState;
    try {
        editState = JSON.parse(stateElement.textContent);
    } catch (_error) {
        return;
    }

    const fieldMap = new Map((editState.fields || []).map((field) => [field.key, { ...field }]));
    const wrappers = new Map();
    const baselineValues = {};
    let editing = false;
    let busy = false;
    let pendingChanges = null;

    const elements = {
        toggle: root.querySelector("[data-entity-edit-toggle]"),
        cancel: root.querySelector("[data-entity-edit-cancel]"),
        submit: root.querySelector("[data-entity-edit-submit]"),
        feedback: root.querySelector("[data-entity-edit-feedback]"),
        modal: root.querySelector("[data-entity-edit-modal]"),
        modalSummary: root.querySelector("[data-entity-edit-summary]"),
        modalReason: root.querySelector("[data-entity-edit-reason]"),
        modalConfirm: root.querySelector("[data-entity-edit-confirm]"),
        modalCloseButtons: Array.from(root.querySelectorAll("[data-entity-edit-modal-close]")),
    };

    const submitUrl = root.dataset.submitUrl;
    const publishUrl = root.dataset.publishUrl;

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

    function escapeHtml(value) {
        return String(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#39;");
    }

    function normalizeValue(value) {
        return value == null ? "" : String(value);
    }

    function formatValue(field, value) {
        const normalized = normalizeValue(value).trim();
        if (!normalized) {
            return "N/A";
        }

        if (field.type === "choice") {
            const choice = (field.choices || []).find((item) => item.value === normalized);
            return choice ? choice.label : normalized;
        }

        if (field.type === "integer") {
            const parsed = Number.parseInt(normalized, 10);
            if (Number.isFinite(parsed)) {
                return parsed.toLocaleString();
            }
        }

        return normalized;
    }

    function setFeedback(message, tone) {
        if (!elements.feedback) {
            return;
        }

        elements.feedback.hidden = !message;
        elements.feedback.textContent = message || "";
        elements.feedback.classList.remove("info", "success", "error");
        elements.feedback.classList.add(tone || "info");
    }

    function buildControl(field) {
        let control;
        if (field.type === "choice") {
            control = document.createElement("select");
            control.className = "input-app select-app entity-edit-control";
            for (const choice of field.choices || []) {
                const option = document.createElement("option");
                option.value = choice.value;
                option.textContent = choice.label;
                control.appendChild(option);
            }
        } else {
            control = document.createElement("input");
            control.className = "input-app entity-edit-control";
            control.type = field.type === "date" ? "date" : field.type === "integer" ? "number" : "text";
            if (field.type === "integer") {
                control.min = "0";
                control.step = "1";
            }
        }

        control.value = normalizeValue(field.value);
        return control;
    }

    function updateDisplay(fieldKey) {
        const field = fieldMap.get(fieldKey);
        if (!field) {
            return;
        }

        const display = formatValue(field, field.value);
        root.querySelectorAll(`[data-edit-display-for="${fieldKey}"]`).forEach((node) => {
            node.textContent = display;
        });

        const wrapper = wrappers.get(fieldKey);
        if (wrapper && wrapper.valueNode) {
            wrapper.valueNode.textContent = display;
        }
    }

    function applyBaseline(resetControls) {
        fieldMap.forEach((field, fieldKey) => {
            field.value = baselineValues[fieldKey];
            updateDisplay(fieldKey);

            if (resetControls) {
                const wrapper = wrappers.get(fieldKey);
                if (wrapper) {
                    wrapper.control.value = normalizeValue(field.value);
                }
            }
        });
    }

    function collectChanges() {
        const changes = {};
        wrappers.forEach((entry, fieldKey) => {
            const nextValue = normalizeValue(entry.control.value).trim();
            if (nextValue !== normalizeValue(baselineValues[fieldKey])) {
                changes[fieldKey] = nextValue;
            }
        });
        return changes;
    }

    function setBusy(nextBusy) {
        busy = nextBusy;
        root.classList.toggle("entity-edit-busy", nextBusy);
        [elements.toggle, elements.cancel, elements.submit, elements.modalConfirm].forEach((button) => {
            if (button) {
                button.disabled = nextBusy;
            }
        });
        wrappers.forEach((entry) => {
            entry.control.disabled = nextBusy;
        });
    }

    function enterEditMode() {
        if (busy) {
            return;
        }

        editing = true;
        root.classList.add("entity-edit-mode");
        if (elements.toggle) {
            elements.toggle.hidden = true;
        }
        if (elements.cancel) {
            elements.cancel.hidden = false;
        }
        if (elements.submit) {
            elements.submit.hidden = false;
        }
        wrappers.forEach((entry, fieldKey) => {
            entry.wrapper.classList.add("is-editing");
            entry.valueNode.hidden = true;
            entry.controlWrap.hidden = false;
            entry.control.value = normalizeValue(baselineValues[fieldKey]);
        });
        setFeedback("", "info");
    }

    function leaveEditMode(resetControls) {
        editing = false;
        root.classList.remove("entity-edit-mode");
        if (elements.toggle) {
            elements.toggle.hidden = false;
        }
        if (elements.cancel) {
            elements.cancel.hidden = true;
        }
        if (elements.submit) {
            elements.submit.hidden = true;
        }
        wrappers.forEach((entry) => {
            entry.wrapper.classList.remove("is-editing");
            entry.valueNode.hidden = false;
            entry.controlWrap.hidden = true;
        });

        if (resetControls) {
            applyBaseline(true);
        }
    }

    function openModal() {
        if (!elements.modal) {
            return;
        }
        elements.modal.hidden = false;
        document.body.classList.add("entity-edit-modal-open");
    }

    function closeModal(force = false) {
        if (!elements.modal || (busy && !force)) {
            return;
        }
        elements.modal.hidden = true;
        document.body.classList.remove("entity-edit-modal-open");
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json();
        if (!response.ok) {
            const error = new Error(data.error || "Request failed.");
            error.payload = data;
            throw error;
        }
        return data;
    }

    async function submitPendingChanges(reason) {
        if (!pendingChanges || Object.keys(pendingChanges).length === 0) {
            setFeedback("No changes to submit.", "error");
            closeModal();
            return;
        }

        setBusy(true);
        try {
            const payload = await postJson(submitUrl, {
                entity_type: editState.entity_type,
                entity_id: editState.entity_id,
                entity_year: editState.entity_year,
                changes: pendingChanges,
                reason,
            });

            if (elements.modalReason) {
                elements.modalReason.value = "";
            }
            closeModal(true);
            leaveEditMode(true);
            pendingChanges = null;
            setFeedback(payload.message || "Suggestion submitted.", "success");
        } catch (error) {
            setFeedback(error.message, "error");
        } finally {
            setBusy(false);
        }
    }

    async function publishChanges(changes) {
        setBusy(true);
        try {
            const payload = await postJson(publishUrl, {
                entity_type: editState.entity_type,
                entity_id: editState.entity_id,
                entity_year: editState.entity_year,
                changes,
            });

            for (const updatedField of payload.updated_fields || []) {
                baselineValues[updatedField.field_key] = normalizeValue(updatedField.value);
            }
            applyBaseline(true);
            leaveEditMode(false);
            setFeedback(payload.message || "Changes published.", "success");
        } catch (error) {
            setFeedback(error.message, "error");
        } finally {
            setBusy(false);
        }
    }

    fieldMap.forEach((field, fieldKey) => {
        baselineValues[fieldKey] = normalizeValue(field.value);
        updateDisplay(fieldKey);
    });

    root.querySelectorAll("[data-edit-field]").forEach((wrapper) => {
        const fieldKey = wrapper.dataset.editField;
        const field = fieldMap.get(fieldKey);
        const valueNode = wrapper.querySelector("[data-edit-value]");

        if (!field || !valueNode) {
            return;
        }

        const controlWrap = document.createElement("div");
        controlWrap.className = "entity-edit-control-wrap";
        controlWrap.hidden = true;

        const control = buildControl(field);
        controlWrap.appendChild(control);
        wrapper.appendChild(controlWrap);

        wrappers.set(fieldKey, {
            wrapper,
            valueNode,
            controlWrap,
            control,
        });
    });

    if (elements.toggle) {
        elements.toggle.addEventListener("click", enterEditMode);
    }

    if (elements.cancel) {
        elements.cancel.addEventListener("click", () => {
            pendingChanges = null;
            leaveEditMode(true);
            setFeedback("", "info");
        });
    }

    if (elements.submit) {
        elements.submit.addEventListener("click", () => {
            const changes = collectChanges();
            if (Object.keys(changes).length === 0) {
                setFeedback("No changes to submit.", "error");
                return;
            }

            if (editState.is_admin) {
                publishChanges(changes);
                return;
            }

            pendingChanges = changes;
            if (elements.modalSummary) {
                const rows = Object.entries(changes).map(([fieldKey, nextValue]) => {
                    const field = fieldMap.get(fieldKey);
                    return `
                        <div class="entity-edit-summary-row">
                            <span>${escapeHtml(field.label)}</span>
                            <strong>${escapeHtml(formatValue(field, baselineValues[fieldKey]))} → ${escapeHtml(formatValue(field, nextValue))}</strong>
                        </div>
                    `;
                });
                elements.modalSummary.innerHTML = rows.join("");
            }
            openModal();
        });
    }

    elements.modalCloseButtons.forEach((button) => {
        button.addEventListener("click", closeModal);
    });

    if (elements.modal) {
        elements.modal.addEventListener("click", (event) => {
            if (event.target === elements.modal) {
                closeModal();
            }
        });
    }

    if (elements.modalConfirm) {
        elements.modalConfirm.addEventListener("click", () => {
            submitPendingChanges((elements.modalReason && elements.modalReason.value.trim()) || "");
        });
    }
})();

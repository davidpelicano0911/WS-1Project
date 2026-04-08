document.addEventListener("DOMContentLoaded", () => {
  const forms = Array.from(document.querySelectorAll("[data-auto-submit-filters]"));
  if (!forms.length) {
    return;
  }

  forms.forEach((form) => {
    const delay = Number(form.dataset.autoSubmitDelay || 300);
    let submitTimer = null;

    const scheduleSubmit = () => {
      window.clearTimeout(submitTimer);
      submitTimer = window.setTimeout(() => {
        if (document.activeElement && document.activeElement.form === form) {
          document.activeElement.blur();
        }
        form.requestSubmit();
      }, delay);
    };

    const submitNow = () => {
      window.clearTimeout(submitTimer);
      form.requestSubmit();
    };

    form.addEventListener("input", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement)) {
        return;
      }

      if (target.type === "text" || target.type === "search") {
        scheduleSubmit();
        return;
      }

      if (target.type === "checkbox") {
        submitNow();
        return;
      }
    });

    form.addEventListener("change", (event) => {
      const target = event.target;
      if (
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLInputElement && (target.type === "radio" || target.type === "checkbox"))
      ) {
        submitNow();
      }
    });

    form.addEventListener("submit", () => {
      window.clearTimeout(submitTimer);
    });
  });
});

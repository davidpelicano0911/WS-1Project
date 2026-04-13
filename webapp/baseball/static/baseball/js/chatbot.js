(() => {
  const root = document.querySelector("[data-chatbot-root]");
  if (!root) return;

  const panel = root.querySelector("[data-chatbot-panel]");
  const toggle = root.querySelector("[data-chatbot-toggle]");
  const close = root.querySelector("[data-chatbot-close]");
  const form = root.querySelector("[data-chatbot-form]");
  const input = root.querySelector(".chatbot-input");
  const messages = root.querySelector("[data-chatbot-messages]");
  const suggestions = root.querySelector("[data-chatbot-suggestions]");
  const endpoint = root.dataset.chatbotUrl;

  let requestId = 0;

  const escapeHtml = (value) =>
    String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");

  const scrollToBottom = () => {
    messages.scrollTop = messages.scrollHeight;
  };

  const renderSuggestions = (items) => {
    if (!Array.isArray(items) || !items.length) return;
    suggestions.innerHTML = items
      .slice(0, 4)
      .map(
        (item) =>
          `<button type="button" class="chatbot-suggestion" data-chatbot-prompt="${escapeHtml(item)}">${escapeHtml(item)}</button>`
      )
      .join("");
  };

  const appendMessage = (role, html) => {
    const article = document.createElement("article");
    article.className = `chatbot-message chatbot-message-${role}`;
    article.innerHTML = `<div class="chatbot-bubble">${html}</div>`;
    messages.appendChild(article);
    scrollToBottom();
    return article;
  };

  const renderItems = (items) => {
    if (!Array.isArray(items) || !items.length) return "";
    return `
      <div class="chatbot-result-list">
        ${items
          .map(
            (item) => `
              <a class="chatbot-result" href="${escapeHtml(item.url)}">
                <div>
                  <div class="chatbot-result-label">${escapeHtml(item.label)}</div>
                  <div class="chatbot-result-meta">${escapeHtml(item.meta || "")}</div>
                </div>
                <span class="chatbot-result-kind">${escapeHtml(item.kind || "Result")}</span>
              </a>
            `
          )
          .join("")}
      </div>
    `;
  };

  const setOpen = (open) => {
    root.classList.toggle("is-open", open);
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      window.requestAnimationFrame(() => input.focus());
      scrollToBottom();
    }
  };

  const sendPrompt = async (prompt) => {
    const query = String(prompt || "").trim();
    if (!query) return;

    appendMessage("user", escapeHtml(query));
    const thinking = appendMessage("assistant", "Thinking with GraphDB…");
    input.value = "";

    const currentRequest = ++requestId;
    try {
      const response = await fetch(`${endpoint}?q=${encodeURIComponent(query)}`, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      if (!response.ok || currentRequest !== requestId) {
        thinking.remove();
        return;
      }
      const payload = await response.json();
      if (currentRequest !== requestId) {
        thinking.remove();
        return;
      }
      thinking.remove();
      appendMessage(
        "assistant",
        `
          <div>${escapeHtml(payload.answer || "No response available.")}</div>
          ${renderItems(payload.items || [])}
        `
      );
      renderSuggestions(payload.suggestions || []);
    } catch (error) {
      thinking.remove();
      appendMessage(
        "assistant",
        "The assistant could not reach GraphDB right now. Try again in a moment."
      );
    }
  };

  toggle.addEventListener("click", () => {
    setOpen(!root.classList.contains("is-open"));
  });

  close.addEventListener("click", () => setOpen(false));

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendPrompt(input.value);
  });

  suggestions.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chatbot-prompt]");
    if (!button) return;
    sendPrompt(button.dataset.chatbotPrompt);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && root.classList.contains("is-open")) {
      setOpen(false);
    }
  });
})();

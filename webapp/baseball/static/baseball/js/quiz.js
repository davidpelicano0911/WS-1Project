(function () {
    const app = document.getElementById("quiz-app");
    if (!app) {
        return;
    }

    const pageMode = app.dataset.pageMode || "landing";
    const isPlayPage = pageMode === "play";

    const OPTION_MARKS = ["◆", "●", "▲", "■"];
    const HERO_BUTTON_COPY = {
        start: "Start round",
        resume: "Resume round",
        results: "View results",
        loading: "Loading...",
    };

    const state = {
        currentQuestion: null,
        pendingNextQuestion: null,
        pendingSummary: null,
        lastSummary: null,
        score: 0,
        total: 10,
        busy: false,
        hasStoredRound: false,
        completed: false,
    };

    const elements = {
        modal: document.getElementById("quiz-modal"),
        modalStage: document.querySelector(".quiz-modal-stage"),
        loading: document.getElementById("quiz-loading"),
        loadingText: document.getElementById("quiz-loading-text"),
        live: document.getElementById("quiz-live"),
        summary: document.getElementById("quiz-summary"),
        error: document.getElementById("quiz-error"),
        startButton: document.getElementById("quiz-start-button"),
        startHero: document.getElementById("quiz-start-hero"),
        restartButton: document.getElementById("quiz-restart-button"),
        closeButton: document.getElementById("quiz-close-button"),
        summaryClose: document.getElementById("quiz-summary-close"),
        progressCurrent: document.getElementById("quiz-progress-current"),
        progressTotal: document.getElementById("quiz-progress-total"),
        scoreValue: document.getElementById("quiz-score-value"),
        categoryChip: document.getElementById("quiz-category-chip"),
        prompt: document.getElementById("quiz-prompt"),
        context: document.getElementById("quiz-context"),
        options: document.getElementById("quiz-options"),
        feedback: document.getElementById("quiz-feedback"),
        feedbackTitle: document.getElementById("quiz-feedback-title"),
        feedbackText: document.getElementById("quiz-feedback-text"),
        nextButton: document.getElementById("quiz-next-button"),
        summaryPoints: document.getElementById("quiz-summary-points"),
        summaryPercent: document.getElementById("quiz-summary-percent"),
        summaryCopy: document.getElementById("quiz-summary-copy"),
        leaderboardBody: document.getElementById("quiz-leaderboard-body"),
        personalRank: document.getElementById("quiz-personal-rank"),
    };

    function animateStageResize(mutator) {
        if (!elements.modalStage) {
            mutator();
            return;
        }

        const stage = elements.modalStage;
        const startHeight = stage.getBoundingClientRect().height;
        mutator();
        const endHeight = stage.scrollHeight;

        if (Math.abs(startHeight - endHeight) < 2) {
            return;
        }

        stage.style.height = `${startHeight}px`;
        stage.classList.add("is-resizing");
        stage.getBoundingClientRect();
        stage.style.height = `${endHeight}px`;

        const cleanup = () => {
            stage.style.height = "";
            stage.classList.remove("is-resizing");
            stage.removeEventListener("transitionend", cleanup);
        };

        stage.addEventListener("transitionend", cleanup);
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

    function openModal() {
        if (isPlayPage) {
            if (elements.modal) {
                document.body.classList.add("quiz-modal-open");
                elements.modal.hidden = false;
                elements.modal.setAttribute("aria-hidden", "false");
            }
            return;
        }
        if (!elements.modal) {
            return;
        }
        document.body.classList.add("quiz-modal-open");
        elements.modal.hidden = false;
        elements.modal.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
        if (isPlayPage) {
            if (!state.busy) {
                window.location.assign("/quiz/");
            }
            return;
        }
        if (!elements.modal || state.busy) {
            return;
        }
        document.body.classList.remove("quiz-modal-open");
        elements.modal.hidden = true;
        elements.modal.setAttribute("aria-hidden", "true");
    }

    function setHeroButtons(mode) {
        const heroText = HERO_BUTTON_COPY[mode] || HERO_BUTTON_COPY.start;
        if (elements.startHero) {
            elements.startHero.innerHTML = `<i class="bi bi-play-fill"></i>${heroText}`;
        }
        if (elements.startButton) {
            elements.startButton.textContent = heroText;
        }
    }

    function setBusy(busy) {
        state.busy = busy;
        app.classList.toggle("quiz-shell-busy", busy);
        if (elements.startButton) {
            elements.startButton.disabled = busy;
        }
        if (elements.startHero) {
            elements.startHero.disabled = busy;
        }
        if (elements.restartButton) {
            elements.restartButton.disabled = busy;
        }
        if (elements.nextButton) {
            elements.nextButton.disabled = busy;
        }
        if (elements.closeButton) {
            elements.closeButton.disabled = busy;
        }
        if (elements.summaryClose) {
            elements.summaryClose.disabled = busy;
        }
        if (busy) {
            setHeroButtons("loading");
        } else if (state.completed) {
            setHeroButtons("results");
        } else if (state.hasStoredRound) {
            setHeroButtons("resume");
        } else {
            setHeroButtons("start");
        }
    }

    function setHud(progressCurrent, progressTotal, score, category) {
        elements.progressCurrent.textContent = progressCurrent;
        elements.progressTotal.textContent = progressTotal;
        elements.scoreValue.textContent = score;
        elements.categoryChip.textContent = category || "Ready";
    }

    function showLoading(text) {
        openModal();
        if (elements.modalStage) {
            elements.modalStage.classList.remove("is-summary-mode");
        }
        hideError();
        elements.loading.hidden = false;
        elements.live.hidden = true;
        elements.summary.hidden = true;
        elements.feedback.hidden = true;
        elements.loadingText.textContent = text || "Loading questions...";
    }

    function showError(message) {
        openModal();
        elements.error.hidden = false;
        elements.error.textContent = message;
    }

    function hideError() {
        elements.error.hidden = true;
        elements.error.textContent = "";
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken"),
                Accept: "application/json",
            },
            body: JSON.stringify(payload || {}),
        });
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json")
            ? await response.json()
            : { error: "The server returned an invalid response." };
        if (!response.ok) {
            const error = new Error(data.error || "Request failed.");
            error.payload = data;
            throw error;
        }
        return data;
    }

    async function getJson(url) {
        const response = await fetch(url, {
            headers: { Accept: "application/json" },
        });
        const contentType = response.headers.get("content-type") || "";
        const data = contentType.includes("application/json")
            ? await response.json()
            : { error: "The server returned an invalid response." };
        if (!response.ok) {
            throw new Error(data.error || "Request failed.");
        }
        return data;
    }

    function renderLeaderboard(leaderboard) {
        if (!leaderboard || !elements.leaderboardBody) {
            return;
        }

        if (!leaderboard.entries || leaderboard.entries.length === 0) {
            elements.leaderboardBody.innerHTML = `
                <tr class="is-empty">
                    <td colspan="4">No recorded scores yet.</td>
                </tr>
            `;
        } else {
            elements.leaderboardBody.innerHTML = leaderboard.entries
                .map((entry) => `
                    <tr${leaderboard.current_user_entry && entry.user_id === leaderboard.current_user_entry.user_id ? ' class="is-current-user"' : ""}>
                        <td>#${entry.rank}</td>
                        <td>${entry.username}</td>
                        <td>${entry.best_score}/10 <span>${entry.best_percentage}%</span></td>
                        <td>${entry.attempts}</td>
                    </tr>
                `)
                .join("");
        }

        if (!elements.personalRank) {
            return;
        }

        if (leaderboard.current_user_entry) {
            elements.personalRank.innerHTML = `
                <span class="quiz-personal-rank-label">Your best</span>
                <strong class="quiz-personal-rank-value">#${leaderboard.current_user_entry.rank}</strong>
                <span class="quiz-personal-rank-copy">${leaderboard.current_user_entry.best_score}/10 · ${leaderboard.current_user_entry.best_percentage}%</span>
            `;
        } else {
            elements.personalRank.remove();
            elements.personalRank = null;
        }
    }

    function resetStoredRoundState() {
        state.currentQuestion = null;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;
        state.lastSummary = null;
        state.score = 0;
        state.total = 10;
        state.hasStoredRound = false;
        state.completed = false;
        setHud(0, state.total, 0, "Ready");
        setHeroButtons("start");
    }

    function createOptionButton(option, index) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `quiz-option quiz-option-theme-${index}`;
        button.dataset.optionId = option.id;
        button.innerHTML = `
            <span class="quiz-option-mark">${OPTION_MARKS[index] || OPTION_MARKS[0]}</span>
            <span class="quiz-option-content">
                <span class="quiz-option-label">${option.label}</span>
                <span class="quiz-option-detail${option.detail ? "" : " is-empty"}">${option.detail || ""}</span>
            </span>
        `;
        button.addEventListener("click", () => submitAnswer(option.id));
        return button;
    }

    function renderQuestion(question, score) {
        state.currentQuestion = question;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;
        state.lastSummary = null;
        state.score = score;
        state.total = question.total_questions || state.total;
        state.hasStoredRound = true;
        state.completed = false;

        openModal();
        if (elements.modalStage) {
            elements.modalStage.classList.remove("is-summary-mode");
        }
        animateStageResize(() => {
            hideError();
            elements.loading.hidden = true;
            elements.summary.hidden = true;
            elements.live.hidden = false;
            elements.feedback.hidden = true;
            elements.prompt.textContent = question.prompt;
            elements.context.textContent = question.context;
            elements.options.innerHTML = "";
            question.options.forEach((option, index) => {
                elements.options.appendChild(createOptionButton(option, index));
            });
        });
        setHud(question.question_number, question.total_questions, score, question.category);
        setHeroButtons("resume");
    }

    function renderSummary(summary) {
        state.currentQuestion = null;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;
        state.lastSummary = summary;
        state.score = summary.score;
        state.total = summary.total_questions;
        state.hasStoredRound = true;
        state.completed = true;

        openModal();
        if (elements.modalStage) {
            elements.modalStage.classList.add("is-summary-mode");
        }
        animateStageResize(() => {
            hideError();
            elements.loading.hidden = true;
            elements.live.hidden = true;
            elements.summary.hidden = false;
            elements.summaryPoints.textContent = `${summary.score}/${summary.total_questions}`;
            elements.summaryPercent.textContent = `${summary.percentage}%`;
            elements.summaryCopy.textContent = summary.copy;
        });
        setHud(summary.total_questions, summary.total_questions, summary.score, "Complete");
        setHeroButtons("results");
    }

    function paintAnsweredState(responsePayload) {
        const buttons = Array.from(elements.options.querySelectorAll(".quiz-option"));
        buttons.forEach((button) => {
            button.disabled = true;
            button.classList.add("show-detail");
            const optionId = button.dataset.optionId;
            if (optionId === responsePayload.correct_option_id) {
                button.classList.add("is-correct");
            } else if (
                optionId === responsePayload.selected_option_id &&
                !responsePayload.is_correct
            ) {
                button.classList.add("is-wrong");
            } else {
                button.classList.add("is-muted");
            }
        });
    }

    function resumeExistingRound() {
        if (state.completed && state.lastSummary) {
            renderSummary(state.lastSummary);
            return true;
        }
        if (state.currentQuestion) {
            renderQuestion(state.currentQuestion, state.score);
            return true;
        }
        return false;
    }

    async function startRound(forceNewRound) {
        if (state.busy) {
            return;
        }

        if (!forceNewRound && state.hasStoredRound && resumeExistingRound()) {
            return;
        }

        setBusy(true);
        showLoading("Loading questions...");
        try {
            const payload = await postJson(app.dataset.startUrl, {});
            state.total = payload.total_questions || 10;
            renderQuestion(payload.current_question, payload.score || 0);
        } catch (error) {
            showError(error.message);
        } finally {
            setBusy(false);
        }
    }

    async function submitAnswer(selectedOptionId) {
        if (state.busy || !state.currentQuestion) {
            return;
        }

        setBusy(true);
        hideError();
        try {
            const payload = await postJson(app.dataset.answerUrl, {
                question_id: state.currentQuestion.id,
                selected_option_id: selectedOptionId,
            });
            state.score = payload.score;
            state.pendingNextQuestion = payload.next_question || null;
            state.pendingSummary = payload.summary || null;
            if (payload.leaderboard) {
                renderLeaderboard(payload.leaderboard);
            }

            animateStageResize(() => {
                paintAnsweredState(payload);
                elements.feedback.hidden = false;
                elements.feedback.classList.toggle("is-correct", !!payload.is_correct);
                elements.feedback.classList.toggle("is-wrong", !payload.is_correct);
                elements.feedbackTitle.textContent = payload.is_correct ? "Correct" : "Not quite";
                elements.feedbackText.textContent = payload.explanation;
                elements.nextButton.textContent = payload.completed ? "See results" : "Continue";
            });
        } catch (error) {
            showError(error.message);
        } finally {
            setBusy(false);
        }
    }

    async function restoreState() {
        setBusy(true);
        hideError();
        try {
            const payload = await getJson(app.dataset.stateUrl);
            if (!payload.active) {
                resetStoredRoundState();
                if (isPlayPage) {
                    await startRound(true);
                    return;
                }
                closeModal();
                return;
            }
            state.total = payload.total_questions || 10;
            if (payload.completed && payload.summary) {
                if (payload.leaderboard) {
                    renderLeaderboard(payload.leaderboard);
                }
                renderSummary(payload.summary);
                return;
            }
            renderQuestion(payload.current_question, payload.score || 0);
        } catch (error) {
            resetStoredRoundState();
            if (!isPlayPage) {
                closeModal();
            }
            showError(error.message);
        } finally {
            setBusy(false);
        }
    }

    if (!isPlayPage && elements.startButton) {
        elements.startButton.addEventListener("click", () => startRound(false));
    }
    if (!isPlayPage && elements.startHero) {
        elements.startHero.addEventListener("click", () => startRound(false));
    }
    if (elements.restartButton) {
        elements.restartButton.addEventListener("click", () => startRound(true));
    }
    if (elements.nextButton) {
        elements.nextButton.addEventListener("click", () => {
            if (state.pendingSummary) {
                renderSummary(state.pendingSummary);
                return;
            }
            if (state.pendingNextQuestion) {
                renderQuestion(state.pendingNextQuestion, state.score);
            }
        });
    }
    if (elements.closeButton) {
        elements.closeButton.addEventListener("click", closeModal);
    }
    if (elements.summaryClose && elements.summaryClose.tagName === "BUTTON") {
        elements.summaryClose.addEventListener("click", closeModal);
    }
    if (!isPlayPage && elements.modal) {
        elements.modal.addEventListener("click", (event) => {
            if (event.target === elements.modal) {
                closeModal();
            }
        });
    }
    document.addEventListener("keydown", (event) => {
        if (!isPlayPage && event.key === "Escape" && elements.modal && !elements.modal.hidden) {
            closeModal();
        }
    });

    resetStoredRoundState();
    if (isPlayPage) {
        openModal();
    }
    restoreState();
}());

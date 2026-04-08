(function () {
    const app = document.getElementById("quiz-app");
    if (!app) {
        return;
    }

    const state = {
        currentQuestion: null,
        pendingNextQuestion: null,
        pendingSummary: null,
        score: 0,
        total: 10,
        busy: false,
    };

    const elements = {
        intro: document.getElementById("quiz-intro"),
        live: document.getElementById("quiz-live"),
        summary: document.getElementById("quiz-summary"),
        error: document.getElementById("quiz-error"),
        startButton: document.getElementById("quiz-start-button"),
        startHero: document.getElementById("quiz-start-hero"),
        restartButton: document.getElementById("quiz-restart-button"),
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
    }

    function showError(message) {
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
            },
            body: JSON.stringify(payload || {}),
        });
        const data = await response.json();
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
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Request failed.");
        }
        return data;
    }

    function setHud(progressCurrent, progressTotal, score, category) {
        elements.progressCurrent.textContent = progressCurrent;
        elements.progressTotal.textContent = progressTotal;
        elements.scoreValue.textContent = score;
        elements.categoryChip.textContent = category || "Ready";
    }

    function showPanel(name) {
        elements.intro.hidden = name !== "intro";
        elements.live.hidden = name !== "live";
        elements.summary.hidden = name !== "summary";
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
        }
    }

    function renderIntro() {
        state.currentQuestion = null;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;
        setHud(0, state.total, 0, "Ready");
        hideError();
        showPanel("intro");
    }

    function createOptionButton(option) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quiz-option";
        button.dataset.optionId = option.id;
        button.innerHTML = `
            <span class="quiz-option-label">${option.label}</span>
            <span class="quiz-option-detail${option.detail ? "" : " is-empty"}">${option.detail || ""}</span>
        `;
        button.addEventListener("click", () => submitAnswer(option.id));
        return button;
    }

    function renderQuestion(question, score) {
        state.currentQuestion = question;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;
        state.score = score;

        hideError();
        showPanel("live");
        elements.feedback.hidden = true;
        elements.prompt.textContent = question.prompt;
        elements.context.textContent = question.context;
        elements.options.innerHTML = "";
        question.options.forEach((option) => {
            elements.options.appendChild(createOptionButton(option));
        });
        setHud(
            question.question_number,
            question.total_questions,
            score,
            question.category
        );
    }

    function renderSummary(summary) {
        state.currentQuestion = null;
        state.pendingNextQuestion = null;
        state.pendingSummary = null;

        hideError();
        showPanel("summary");
        elements.summaryPoints.textContent = `${summary.score}/${summary.total_questions}`;
        elements.summaryPercent.textContent = `${summary.percentage}%`;
        elements.summaryCopy.textContent = summary.copy;
        setHud(summary.total_questions, summary.total_questions, summary.score, "Complete");
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

    async function startRound() {
        setBusy(true);
        hideError();
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

            paintAnsweredState(payload);
            elements.feedback.hidden = false;
            elements.feedbackTitle.textContent = payload.is_correct ? "Correct" : "Not quite";
            elements.feedbackText.textContent = payload.explanation;
            elements.nextButton.textContent = payload.completed ? "See results" : "Continue";
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
                renderIntro();
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
            showError(error.message);
            renderIntro();
        } finally {
            setBusy(false);
        }
    }

    if (elements.startButton) {
        elements.startButton.addEventListener("click", startRound);
    }
    if (elements.startHero) {
        elements.startHero.addEventListener("click", startRound);
    }
    if (elements.restartButton) {
        elements.restartButton.addEventListener("click", startRound);
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

    restoreState();
}());

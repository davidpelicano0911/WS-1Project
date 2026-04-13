(() => {
    const tabsRoot = document.getElementById("analytics-tabs");
    if (!tabsRoot) {
        return;
    }

    const charts = {};
    const currencyFormatter = new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
    });

    const compactNumberFormatter = new Intl.NumberFormat("en-US", {
        notation: "compact",
        maximumFractionDigits: 1,
    });

    const chartPalette = [
        "#1d4f91",
        "#c63845",
        "#d9a728",
        "#1f8c7a",
        "#7b61ff",
        "#e57a44",
        "#5476a5",
        "#33a66f",
    ];

    const chartBorderPalette = [
        "#153b6c",
        "#8f2134",
        "#b28215",
        "#16695b",
        "#5940ce",
        "#c65c28",
        "#365784",
        "#278257",
    ];

    const readJsonScript = (id) => {
        const element = document.getElementById(id);
        if (!element) {
            return [];
        }
        try {
            return JSON.parse(element.textContent);
        } catch (_error) {
            return [];
        }
    };

    const salaryRows = readJsonScript("analytics-salary-trends-data");
    const franchiseRows = readJsonScript("analytics-franchise-history-data");
    const awardsRows = readJsonScript("analytics-awards-timeline-data");
    const awardsCatalogRows = readJsonScript("analytics-awards-catalog-data");
    const hallRows = readJsonScript("analytics-hall-timeline-data");
    const awardsTableState = {
        currentPage: 1,
        pageSize: 15,
    };

    const salaryMetricLabels = {
        total_salary: "Total salary paid",
        avg_salary: "Average salary",
        max_salary: "Highest recorded salary",
    };

    const getSelectValue = (id, fallback = "") => {
        const element = document.getElementById(id);
        return element ? element.value : fallback;
    };

    const setChartState = (canvasId, emptyId, hasData) => {
        const canvas = document.getElementById(canvasId);
        const emptyState = document.getElementById(emptyId);
        if (canvas) {
            canvas.hidden = !hasData;
        }
        if (emptyState) {
            emptyState.hidden = hasData;
        }
    };

    const replaceChart = (key, canvasId, config, emptyId) => {
        const canvas = document.getElementById(canvasId);
        if (!canvas || typeof Chart === "undefined") {
            setChartState(canvasId, emptyId, false);
            return;
        }

        if (charts[key]) {
            charts[key].destroy();
        }

        charts[key] = new Chart(canvas, config);
        setChartState(canvasId, emptyId, true);
    };

    const destroyChart = (key, canvasId, emptyId) => {
        if (charts[key]) {
            charts[key].destroy();
            delete charts[key];
        }
        setChartState(canvasId, emptyId, false);
    };

    const buildLineDataset = (label, values, color) => ({
        label,
        data: values,
        borderColor: color,
        backgroundColor: `${color}33`,
        tension: 0.24,
        fill: true,
        borderWidth: 3,
        pointRadius: 2,
        pointHoverRadius: 4,
    });

    const renderSalaryChart = () => {
        const metric = getSelectValue("analytics-salary-metric", "total_salary");
        const labels = salaryRows.map((row) => row.year);
        const values = salaryRows.map((row) => Number(row[metric] ?? 0));

        if (!labels.length) {
            destroyChart("salary", "analytics-salary-chart", "analytics-salary-empty");
            return;
        }

        replaceChart(
            "salary",
            "analytics-salary-chart",
            {
                type: "line",
                data: {
                    labels,
                    datasets: [buildLineDataset(salaryMetricLabels[metric] || "Salary", values, "#33a66f")],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: "index",
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    return `${context.dataset.label}: ${currencyFormatter.format(context.parsed.y || 0)}`;
                                },
                                afterLabel(context) {
                                    const row = salaryRows[context.dataIndex];
                                    return row ? `Paid players: ${row.paid_players}` : "";
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 12,
                            },
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                        },
                        y: {
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                            ticks: {
                                callback(value) {
                                    return compactNumberFormatter.format(value);
                                },
                            },
                        },
                    },
                },
            },
            "analytics-salary-empty",
        );
    };

    const renderFranchiseChart = () => {
        const franchiseId = getSelectValue("analytics-franchise-select");
        const rows = franchiseRows.filter((row) => row.franch_id === franchiseId);

        if (!rows.length) {
            destroyChart("franchise", "analytics-franchise-chart", "analytics-franchise-empty");
            return;
        }

        const labels = rows.map((row) => row.year);
        const values = rows.map((row) => Number(row.win_pct ?? 0));
        const franchiseName = rows[0].franch_name || franchiseId;

        replaceChart(
            "franchise",
            "analytics-franchise-chart",
            {
                type: "line",
                data: {
                    labels,
                    datasets: [buildLineDataset(`${franchiseName} · Win percentage`, values, "#1d4f91")],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {
                        mode: "index",
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    const value = context.parsed.y;
                                    return `${context.dataset.label}: ${(value * 100).toFixed(1)}%`;
                                },
                                afterLabel(context) {
                                    const row = rows[context.dataIndex];
                                    if (!row) {
                                        return "";
                                    }
                                    return `Record: ${row.wins}-${row.losses} · Runs: ${row.runs} · Allowed: ${row.runs_allowed}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            ticks: {
                                maxRotation: 0,
                                autoSkip: true,
                                maxTicksLimit: 12,
                            },
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                        },
                        y: {
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                            ticks: {
                                callback(value) {
                                    return `${(value * 100).toFixed(0)}%`;
                                },
                            },
                        },
                    },
                },
            },
            "analytics-franchise-empty",
        );
    };

    const renderAwardsChart = () => {
        const selectedLeague = getSelectValue("analytics-league-filter");
        const filteredRows = awardsRows.filter((row) => {
            const matchesLeague = !selectedLeague || row.league === selectedLeague;
            return matchesLeague;
        });

        if (!filteredRows.length) {
            destroyChart("awards", "analytics-awards-chart", "analytics-awards-empty");
            return;
        }

        const years = Array.from(new Set(filteredRows.map((row) => row.year))).sort((left, right) => left - right);
        const totals = new Map();

        filteredRows.forEach((row) => {
            totals.set(row.year, (totals.get(row.year) || 0) + Number(row.count || 0));
        });

        replaceChart(
            "awards",
            "analytics-awards-chart",
            {
                type: "bar",
                data: {
                    labels: years,
                    datasets: [
                        {
                            label: "Awards granted",
                            data: years.map((year) => totals.get(year) || 0),
                            backgroundColor: "#7b61ffcc",
                            borderColor: "#5940ce",
                            borderWidth: 1,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    return `${context.dataset.label}: ${context.parsed.y}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                        },
                        y: {
                            beginAtZero: true,
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                            ticks: {
                                precision: 0,
                            },
                        },
                    },
                },
            },
            "analytics-awards-empty",
        );
    };

    const renderHallChart = () => {
        if (!hallRows.length) {
            destroyChart("hall", "analytics-hall-chart", "analytics-hall-empty");
            return;
        }

        replaceChart(
            "hall",
            "analytics-hall-chart",
            {
                type: "bar",
                data: {
                    labels: hallRows.map((row) => row.year),
                    datasets: [
                        {
                            label: "Inducted players",
                            data: hallRows.map((row) => Number(row.inducted_count || 0)),
                            backgroundColor: "#d9a728cc",
                            borderColor: "#b28215",
                            borderWidth: 1,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false,
                        },
                        tooltip: {
                            callbacks: {
                                label(context) {
                                    return `${context.dataset.label}: ${context.parsed.y}`;
                                },
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                        },
                        y: {
                            beginAtZero: true,
                            ticks: {
                                precision: 0,
                            },
                            grid: {
                                color: "rgba(17, 52, 98, 0.08)",
                            },
                        },
                    },
                },
            },
            "analytics-hall-empty",
        );
    };

    const renderAwardsTable = () => {
        const selectedYear = getSelectValue("analytics-awards-table-year");
        const selectedAward = getSelectValue("analytics-awards-table-award");
        const selectedLeague = getSelectValue("analytics-awards-table-league");
        const tableBody = document.getElementById("analytics-awards-table-body");
        const emptyState = document.getElementById("analytics-awards-table-empty");
        const pagination = document.getElementById("analytics-awards-pagination");
        const previousButton = document.getElementById("analytics-awards-prev");
        const nextButton = document.getElementById("analytics-awards-next");
        const pagesContainer = document.getElementById("analytics-awards-pages");

        if (!tableBody || !emptyState || !pagination || !previousButton || !nextButton || !pagesContainer) {
            return;
        }

        const filteredRows = awardsCatalogRows.filter((row) => {
            const matchesYear = !selectedYear || String(row.year) === selectedYear;
            const matchesAward = !selectedAward || row.award_name === selectedAward;
            const matchesLeague = !selectedLeague || row.league === selectedLeague;
            return matchesYear && matchesAward && matchesLeague;
        });

        const totalPages = Math.max(Math.ceil(filteredRows.length / awardsTableState.pageSize), 1);
        awardsTableState.currentPage = Math.min(awardsTableState.currentPage, totalPages);
        awardsTableState.currentPage = Math.max(awardsTableState.currentPage, 1);

        const start = (awardsTableState.currentPage - 1) * awardsTableState.pageSize;
        const pageRows = filteredRows.slice(start, start + awardsTableState.pageSize);

        if (!pageRows.length) {
            tableBody.innerHTML = "";
            emptyState.hidden = false;
            pagination.hidden = true;
            return;
        }

        emptyState.hidden = true;
        pagination.hidden = false;
        tableBody.innerHTML = pageRows.map((row) => {
            const playerCell = row.player_id
                ? `<a href="/players/${encodeURIComponent(row.player_id)}/" class="fw-bold text-white text-decoration-none">${row.name}</a>`
                : `<strong>${row.name}</strong>`;
            return `
                <tr>
                    <td class="text-start">${playerCell}</td>
                    <td class="text-start">${row.award_name}</td>
                    <td><span class="pill">${row.year}</span></td>
                    <td>${row.league || "-"}</td>
                </tr>
            `;
        }).join("");

        previousButton.disabled = awardsTableState.currentPage <= 1;
        nextButton.disabled = awardsTableState.currentPage >= totalPages;

        const firstPage = Math.max(1, awardsTableState.currentPage - 2);
        const lastPage = Math.min(totalPages, awardsTableState.currentPage + 2);
        const pageNumbers = [];
        for (let page = firstPage; page <= lastPage; page += 1) {
            pageNumbers.push(page);
        }

        pagesContainer.innerHTML = pageNumbers.map((page) => (
            `<button type="button" class="pager-page${page === awardsTableState.currentPage ? " active" : ""}" data-awards-page="${page}">${page}</button>`
        )).join("");

        pagesContainer.querySelectorAll("[data-awards-page]").forEach((button) => {
            button.addEventListener("click", () => {
                awardsTableState.currentPage = Number(button.getAttribute("data-awards-page")) || 1;
                renderAwardsTable();
            });
        });
    };

    const renderers = {
        "teams-stats": renderFranchiseChart,
        "salaries-stats": renderSalaryChart,
        "awards-stats": renderAwardsChart,
        "hall-stats": renderHallChart,
    };

    const resizeCharts = () => {
        Object.values(charts).forEach((chart) => chart.resize());
    };

    tabsRoot.querySelectorAll(".btn-app").forEach((button) => {
        button.addEventListener("shown.bs.tab", (event) => {
            tabsRoot.querySelectorAll(".btn-app").forEach((tabButton) => {
                tabButton.classList.remove("btn-primary-app");
                tabButton.classList.add("btn-secondary-app");
            });

            event.target.classList.remove("btn-secondary-app");
            event.target.classList.add("btn-primary-app");

            const targetSelector = event.target.getAttribute("data-bs-target");
            const targetId = targetSelector ? targetSelector.replace("#", "") : "";
            if (!targetId || !renderers[targetId]) {
                return;
            }

            window.setTimeout(() => {
                renderers[targetId]();
                resizeCharts();
            }, 60);
        });
    });

    [
        ["analytics-salary-metric", renderSalaryChart],
        ["analytics-franchise-select", renderFranchiseChart],
        ["analytics-league-filter", renderAwardsChart],
    ].forEach(([id, handler]) => {
        const element = document.getElementById(id);
        if (!element) {
            return;
        }
        element.addEventListener("change", handler);
    });

    [
        "analytics-awards-table-year",
        "analytics-awards-table-award",
        "analytics-awards-table-league",
    ].forEach((id) => {
        const element = document.getElementById(id);
        if (!element) {
            return;
        }
        element.addEventListener("change", () => {
            awardsTableState.currentPage = 1;
            renderAwardsTable();
        });
    });

    const awardsPreviousButton = document.getElementById("analytics-awards-prev");
    if (awardsPreviousButton) {
        awardsPreviousButton.addEventListener("click", () => {
            awardsTableState.currentPage = Math.max(1, awardsTableState.currentPage - 1);
            renderAwardsTable();
        });
    }

    const awardsNextButton = document.getElementById("analytics-awards-next");
    if (awardsNextButton) {
        awardsNextButton.addEventListener("click", () => {
            awardsTableState.currentPage += 1;
            renderAwardsTable();
        });
    }

    window.addEventListener("resize", resizeCharts);

    if (typeof Chart !== "undefined") {
        Chart.defaults.color = "#173045";
        Chart.defaults.font.family = "Barlow, sans-serif";
        Chart.defaults.plugins.tooltip.backgroundColor = "rgba(14, 32, 57, 0.94)";
        Chart.defaults.plugins.tooltip.titleColor = "#f5f8ff";
        Chart.defaults.plugins.tooltip.bodyColor = "#f5f8ff";
    }

    document.querySelectorAll(".tab-pane.show.active").forEach((panel) => {
        const render = renderers[panel.id];
        if (render) {
            render();
        }
    });

    renderAwardsTable();
})();

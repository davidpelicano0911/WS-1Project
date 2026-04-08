(() => {
    const graphContainer = document.getElementById("player-graph");
    const nodesElement = document.getElementById("graph-nodes-data");
    const edgesElement = document.getElementById("graph-edges-data");

    if (!graphContainer || !nodesElement || !edgesElement || typeof cytoscape === "undefined") {
        return;
    }

    const nodes = JSON.parse(nodesElement.textContent);
    const edges = JSON.parse(edgesElement.textContent);

    const MLB_LOGO_IDS = {
        ARI: 109, ATL: 144, BAL: 110, BOS: 111, CHC: 112, CHW: 145,
        CIN: 113, CLE: 114, COL: 115, DET: 116, HOU: 117, KCR: 118,
        LAA: 108, LAD: 119, MIA: 146, MIL: 158, MIN: 142, NYM: 121,
        NYY: 147, OAK: 133, PHI: 143, PIT: 134, SDP: 135, SEA: 136,
        SFG: 137, STL: 138, TBR: 139, TEX: 140, TOR: 141, WSN: 120,
    };

    const TEAM_CODE_NORMALIZATION = {
        ANA: "LAA", CAL: "LAA", CHA: "CHW", CHN: "CHC", KCA: "KCR",
        LAN: "LAD", MON: "WSN", NYA: "NYY", NYN: "NYM", SDN: "SDP",
        SFN: "SFG", SLN: "STL", TBA: "TBR",
    };

    nodes.forEach((node) => {
        if (node.data.type !== "team") {
            return;
        }

        const match = node.data.id.match(/\/team\/([A-Z]+)\//);
        if (!match || !match[1]) {
            return;
        }

        const teamCode = match[1];
        const normalizedCode = TEAM_CODE_NORMALIZATION[teamCode] || teamCode;
        const logoId = MLB_LOGO_IDS[normalizedCode];
        if (logoId) {
            node.data.logoUrl = `https://www.mlbstatic.com/team-logos/${logoId}.svg`;
        }
    });

    const cy = cytoscape({
        container: graphContainer,
        elements: [...nodes, ...edges],
        layout: {
            name: "concentric",
            animate: false,
            minNodeSpacing: 44,
            levelWidth: () => 1,
            concentric: (node) => {
                const type = node.data("type");
                if (type === "player") {
                    return 3;
                }
                if (type === "team" || type === "award") {
                    return 2;
                }
                return 1;
            },
        },
        style: [
            {
                selector: "node",
                style: {
                    "background-color": "#1d4f91",
                    label: "data(label)",
                    color: "#ffffff",
                    "text-wrap": "wrap",
                    "text-max-width": 110,
                    "font-size": 11,
                    "font-weight": 700,
                    "text-valign": "bottom",
                    "text-margin-y": 8,
                    width: 28,
                    height: 28,
                    "border-width": 2,
                    "border-color": "#ffffff",
                },
            },
            {
                selector: 'node[type="player"]',
                style: {
                    "background-color": "#c63845",
                    width: 80,
                    height: 80,
                    shape: "ellipse",
                    "border-width": 4,
                    "border-color": "#ffffff",
                    "text-valign": "bottom",
                    "text-margin-y": 10,
                    "text-max-width": 140,
                },
            },
            {
                selector: 'node[type="player"][photoUrl]',
                style: {
                    "background-image": "data(photoUrl)",
                    "background-fit": "cover",
                    "background-repeat": "no-repeat",
                    "background-clip": "node",
                    "background-position-x": "50%",
                    "background-position-y": "50%",
                    "background-opacity": 1,
                    "background-color": "#ffffff",
                },
            },
            {
                selector: 'node[type="team"]',
                style: {
                    "background-color": "#1d4f91",
                    width: 38,
                    height: 38,
                    "border-width": 2,
                    shape: "ellipse",
                },
            },
            {
                selector: 'node[type="team"][logoUrl]',
                style: {
                    "background-color": "#ffffff",
                    "background-fit": "contain",
                    "background-repeat": "no-repeat",
                    "background-clip": "node",
                    "background-image": "data(logoUrl)",
                    "background-position-x": "50%",
                    "background-position-y": "50%",
                    width: 40,
                    height: 40,
                },
            },
            {
                selector: 'node[type="franchise"]',
                style: {
                    "background-color": "#5476a5",
                },
            },
            {
                selector: 'node[type="award"]',
                style: {
                    "background-color": "#d9a728",
                },
            },
            {
                selector: "edge",
                style: {
                    width: 2,
                    "line-color": "#9fb3d1",
                    "target-arrow-color": "#9fb3d1",
                    "target-arrow-shape": "triangle",
                    "curve-style": "bezier",
                },
            },
        ],
        userPanningEnabled: true,
        userZoomingEnabled: true,
        boxSelectionEnabled: false,
    });

    let zoomRefreshFrame = null;
    const refreshImageNodes = () => {
        zoomRefreshFrame = null;
        cy.batch(() => {
            cy.nodes('[photoUrl]').forEach((node) => {
                node.style("background-image", node.data("photoUrl"));
            });
            cy.nodes('[logoUrl]').forEach((node) => {
                node.style("background-image", node.data("logoUrl"));
            });
        });
    };

    cy.on("zoom", () => {
        if (zoomRefreshFrame !== null) {
            cancelAnimationFrame(zoomRefreshFrame);
        }
        zoomRefreshFrame = requestAnimationFrame(refreshImageNodes);
    });

    document.addEventListener("player-detail-tab:change", (event) => {
        if (event.detail?.tab !== "overview") {
            return;
        }
        window.setTimeout(() => {
            cy.resize();
            cy.fit(undefined, 32);
        }, 40);
    });
})();

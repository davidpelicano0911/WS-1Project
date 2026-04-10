(() => {
    const graphContainer = document.getElementById("team-graph");
    const nodesElement = document.getElementById("team-graph-nodes-data");
    const edgesElement = document.getElementById("team-graph-edges-data");

    if (!graphContainer || !nodesElement || !edgesElement || typeof cytoscape === "undefined") {
        return;
    }

    const nodes = JSON.parse(nodesElement.textContent);
    const edges = JSON.parse(edgesElement.textContent);

    const preloadImage = (url) => new Promise((resolve) => {
        if (!url) {
            resolve("");
            return;
        }

        const image = new Image();
        image.onload = () => resolve(url);
        image.onerror = () => resolve("");
        image.src = url;
    });

    const resolveFirstWorkingImage = async (urls) => {
        for (const url of urls) {
            // eslint-disable-next-line no-await-in-loop
            const resolved = await preloadImage(url);
            if (resolved) {
                return resolved;
            }
        }
        return "";
    };

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
        if (node.data.type !== "focus-team" && node.data.type !== "team") {
            return;
        }

        const idMatch = node.data.id.match(/\/team\/([A-Z]+)\//);
        const teamCode = node.data.teamIDBR || node.data.teamID || (idMatch && idMatch[1]) || "";
        if (!teamCode) {
            return;
        }

        const normalizedCode = TEAM_CODE_NORMALIZATION[teamCode] || teamCode;
        const logoId = MLB_LOGO_IDS[normalizedCode];
        if (logoId && !node.data.logoUrl) {
            node.data.logoUrl = `https://www.mlbstatic.com/team-logos/${logoId}.svg`;
        }
    });

    const initializeGraph = () => {
        const cy = cytoscape({
            container: graphContainer,
            elements: [...nodes, ...edges],
            layout: {
                name: "cose",
                animate: false,
                fit: true,
                padding: 72,
                nodeRepulsion: 180000,
                idealEdgeLength: 165,
                edgeElasticity: 90,
                gravity: 0.3,
                nestingFactor: 0.8,
            },
            style: [
                {
                    selector: "node",
                    style: {
                        "background-color": "#1d4f91",
                        label: "data(label)",
                        color: "#ffffff",
                        "text-wrap": "wrap",
                        "text-max-width": 156,
                        "font-size": 12,
                        "font-weight": 700,
                        "text-valign": "bottom",
                        "text-margin-y": 10,
                        "text-background-color": "rgba(9, 24, 48, 0.82)",
                        "text-background-opacity": 1,
                        "text-background-padding": 5,
                        "text-background-shape": "roundrectangle",
                        width: 30,
                        height: 30,
                        "border-width": 2,
                        "border-color": "#ffffff",
                    },
                },
                {
                    selector: 'node[type="focus-team"]',
                    style: {
                        "background-color": "#ffffff",
                        width: 128,
                        height: 128,
                        shape: "ellipse",
                        "border-width": 5,
                        "border-color": "#ffffff",
                        "text-valign": "bottom",
                        "text-margin-y": 14,
                        "text-max-width": 170,
                    },
                },
                {
                    selector: 'node[type="focus-team"][resolvedLogoUrl]',
                    style: {
                        "background-color": "#ffffff",
                        "background-image": "data(resolvedLogoUrl)",
                        "background-fit": "cover",
                        "background-repeat": "no-repeat",
                        "background-clip": "node",
                        "background-position-x": "50%",
                        "background-position-y": "50%",
                        "background-width": "112%",
                        "background-height": "112%",
                        "background-opacity": 1,
                    },
                },
                {
                    selector: 'node[type="player"]',
                    style: {
                        "background-color": "#c63845",
                        width: 52,
                        height: 52,
                        "border-width": 3,
                    },
                },
                {
                    selector: 'node[type="player"][resolvedPhotoUrl]',
                    style: {
                        "background-image": "data(resolvedPhotoUrl)",
                        "background-fit": "cover",
                        "background-repeat": "no-repeat",
                        "background-clip": "node",
                        "background-position-x": "50%",
                        "background-position-y": "34%",
                        "background-width": "112%",
                        "background-height": "112%",
                        "background-opacity": 1,
                        "background-color": "#ffffff",
                    },
                },
                {
                    selector: 'node[type="manager"]',
                    style: {
                        "background-color": "#33a66f",
                        width: 54,
                        height: 54,
                        "border-width": 3,
                    },
                },
                {
                    selector: 'node[type="manager"][resolvedPhotoUrl]',
                    style: {
                        "background-image": "data(resolvedPhotoUrl)",
                        "background-fit": "cover",
                        "background-repeat": "no-repeat",
                        "background-clip": "node",
                        "background-position-x": "50%",
                        "background-position-y": "34%",
                        "background-width": "112%",
                        "background-height": "112%",
                        "background-opacity": 1,
                        "background-color": "#ffffff",
                    },
                },
                {
                    selector: 'node[type="franchise"]',
                    style: {
                        "background-color": "#5476a5",
                        width: 36,
                        height: 36,
                    },
                },
                {
                    selector: 'node[type="league"]',
                    style: {
                        "background-color": "#5a4ea1",
                        width: 34,
                        height: 34,
                    },
                },
                {
                    selector: 'node[type="award"]',
                    style: {
                        "background-color": "#d9a728",
                        width: 34,
                        height: 34,
                    },
                },
                {
                    selector: "edge",
                    style: {
                        width: 2,
                        opacity: 0.65,
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
            minZoom: 0.6,
            maxZoom: 2.4,
            textureOnViewport: false,
        });

        let zoomRefreshFrame = null;
        const refreshImageNodes = () => {
            zoomRefreshFrame = null;
            cy.batch(() => {
                cy.nodes('[resolvedPhotoUrl]').forEach((node) => {
                    node.style("background-image", node.data("resolvedPhotoUrl"));
                });
                cy.nodes('[resolvedLogoUrl]').forEach((node) => {
                    node.style("background-image", node.data("resolvedLogoUrl"));
                });
            });
        };

        const loadGraphImages = async () => {
            await Promise.all(nodes.map(async (rawNode) => {
                const nodeId = rawNode.data.id;
                const cyNode = cy.getElementById(nodeId);
                if (!cyNode || cyNode.empty()) {
                    return;
                }

                if (
                    (rawNode.data.type === "player" || rawNode.data.type === "manager")
                    && (rawNode.data.photoProxyUrl || rawNode.data.photoUrl || rawNode.data.photoFallbackUrl)
                ) {
                    const resolvedPhotoUrl = await resolveFirstWorkingImage([
                        rawNode.data.photoProxyUrl,
                        rawNode.data.photoUrl,
                        rawNode.data.photoFallbackUrl,
                    ]);
                    if (resolvedPhotoUrl) {
                        cyNode.data("resolvedPhotoUrl", resolvedPhotoUrl);
                    }
                }

                if ((rawNode.data.type === "focus-team" || rawNode.data.type === "team") && rawNode.data.logoUrl) {
                    const resolvedLogoUrl = await resolveFirstWorkingImage([rawNode.data.logoUrl]);
                    if (resolvedLogoUrl) {
                        cyNode.data("resolvedLogoUrl", resolvedLogoUrl);
                    }
                }
            }));
            refreshImageNodes();
        };

        cy.on("zoom", () => {
            if (zoomRefreshFrame !== null) {
                cancelAnimationFrame(zoomRefreshFrame);
            }
            zoomRefreshFrame = requestAnimationFrame(refreshImageNodes);
        });

        cy.on("render", () => {
            if (zoomRefreshFrame !== null) {
                return;
            }
            zoomRefreshFrame = requestAnimationFrame(refreshImageNodes);
        });

        refreshImageNodes();
        cy.fit(undefined, 72);
        loadGraphImages();

        document.addEventListener("team-detail-tab:change", (event) => {
            if (event.detail?.tab !== "overview") {
                return;
            }
            window.setTimeout(() => {
                cy.resize();
                cy.fit(undefined, 32);
            }, 40);
        });
    };

    initializeGraph();
})();

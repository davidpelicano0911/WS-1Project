from functools import lru_cache

from .base import _row_value, escape_sparql_string, run_query
def get_player_graph_data(player_id):
    player_id = escape_sparql_string(player_id.strip())
    if not player_id:
        return {"nodes": [], "edges": []}

    player_query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name ?nameFirst ?nameLast ?nameGiven
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        FILTER(?playerID = "{player_id}")
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
    }}
    LIMIT 1
    """

    team_query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?team ?teamName ?teamID ?year ?franchise ?franchiseName
    WHERE {{
        ?player bb:playerID "{player_id}" .
        {{
            ?player bb:hasBatting ?line .
            ?line bb:teamOf ?team .
        }}
        UNION
        {{
            ?player bb:hasPitching ?line .
            ?line bb:teamOf ?team .
        }}
        OPTIONAL {{ ?team bb:teamName ?teamName . }}
        OPTIONAL {{ ?team bb:teamID ?teamID . }}
        OPTIONAL {{ ?team bb:yearID ?year . }}
        OPTIONAL {{
            ?team bb:franchiseOf ?franchise .
            OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}
        }}
    }}
    ORDER BY ?year ?teamName
    """

    award_query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?award ?awardName ?year
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:wonAward ?award .
        OPTIONAL {{ ?award bb:awardName ?awardName . }}
        OPTIONAL {{ ?award bb:yearID ?year . }}
    }}
    ORDER BY ?year ?awardName
    """

    player_results = run_query(player_query)
    if not player_results:
        return {"nodes": [], "edges": []}

    player_row = player_results[0]
    player_node_id = f"player:{player_row['playerID']['value']}"
    player_first = _row_value(player_row, "nameFirst", "")
    player_last = _row_value(player_row, "nameLast", "")
    player_given = _row_value(player_row, "nameGiven", "")
    player_label = " ".join(part for part in [player_first, player_last] if part).strip()
    if not player_label:
        player_label = _row_value(player_row, "name", "") or player_given or player_row["playerID"]["value"]

    nodes = [{
        "data": {
            "id": player_node_id,
            "label": player_label,
            "type": "player",
        }
    }]
    edges = []

    seen_nodes = {player_node_id}
    seen_edges = set()

    for row in run_query(team_query):
        team_uri = row.get("team", {}).get("value")
        if not team_uri:
            continue

        team_node_id = f"team:{team_uri}"
        team_name = row.get("teamName", {}).get("value", "Unknown Team")
        team_id = row.get("teamID", {}).get("value")
        team_year = row.get("year", {}).get("value")
        team_label = f"{team_name} ({team_year})" if team_year else team_name

        if team_node_id not in seen_nodes:
            node_data = {
                "id": team_node_id,
                "label": team_label,
                "type": "team",
            }
            if team_id:
                node_data["teamID"] = team_id
            nodes.append({"data": node_data})
            seen_nodes.add(team_node_id)

        player_team_edge = (player_node_id, team_node_id, "plays_for")
        if player_team_edge not in seen_edges:
            edges.append({
                "data": {
                    "id": f"edge:{player_node_id}->{team_node_id}",
                    "source": player_node_id,
                    "target": team_node_id,
                    "label": "played for",
                }
            })
            seen_edges.add(player_team_edge)

        franchise_uri = row.get("franchise", {}).get("value")
        if not franchise_uri:
            continue

        franchise_node_id = f"franchise:{franchise_uri}"
        franchise_label = row.get("franchiseName", {}).get("value", "Unknown Franchise")

        if franchise_node_id not in seen_nodes:
            nodes.append({
                "data": {
                    "id": franchise_node_id,
                    "label": franchise_label,
                    "type": "franchise",
                }
            })
            seen_nodes.add(franchise_node_id)

        team_franchise_edge = (team_node_id, franchise_node_id, "part_of")
        if team_franchise_edge not in seen_edges:
            edges.append({
                "data": {
                    "id": f"edge:{team_node_id}->{franchise_node_id}",
                    "source": team_node_id,
                    "target": franchise_node_id,
                    "label": "franchise",
                }
            })
            seen_edges.add(team_franchise_edge)

    for row in run_query(award_query):
        award_uri = row.get("award", {}).get("value")
        if not award_uri:
            continue

        award_node_id = f"award:{award_uri}"
        award_name = row.get("awardName", {}).get("value", "Award")
        award_year = row.get("year", {}).get("value")
        award_label = f"{award_name} ({award_year})" if award_year else award_name

        if award_node_id not in seen_nodes:
            nodes.append({
                "data": {
                    "id": award_node_id,
                    "label": award_label,
                    "type": "award",
                }
            })
            seen_nodes.add(award_node_id)

        player_award_edge = (player_node_id, award_node_id, "won")
        if player_award_edge not in seen_edges:
            edges.append({
                "data": {
                    "id": f"edge:{player_node_id}->{award_node_id}",
                    "source": player_node_id,
                    "target": award_node_id,
                    "label": "won",
                }
            })
            seen_edges.add(player_award_edge)

    return {
        "nodes": nodes,
        "edges": edges,
    }

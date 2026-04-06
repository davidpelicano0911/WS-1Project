from functools import lru_cache

from SPARQLWrapper import SPARQLWrapper, JSON

# URL do teu repositório no GraphDB
ENDPOINT = "http://localhost:7200/repositories/baseball"

def run_query(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]

@lru_cache(maxsize=32)
def get_player_options_by_initial(initial):
    initial = str(initial).strip().upper()
    if len(initial) != 1 or not initial.isalpha():
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        FILTER(STRSTARTS(UCASE(STR(?name)), "{initial}"))
    }}
    ORDER BY ?name ?playerID
    """

    results = run_query(query)
    return [
        {
            "player_id": row["playerID"]["value"],
            "name": row["name"]["value"],
        }
        for row in results
    ]

def escape_sparql_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')

@lru_cache(maxsize=1024)
def get_player_summary(player_id):
    player_id = escape_sparql_string(player_id.strip())
    if not player_id:
        return None

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?name ?playerID ?birthYear ?birthCountry ?height ?weight ?awardsCount ?maxSalary ?careerHomeRuns ?careerRBI ?battingSeasons
    WHERE {{
        ?player a bb:Player ;
                foaf:name ?name ;
                bb:playerID ?playerID .
        FILTER(?playerID = "{player_id}")

        OPTIONAL {{ ?player bb:birthYear ?birthYear . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:height ?height . }}
        OPTIONAL {{ ?player bb:weight ?weight . }}

        OPTIONAL {{
            SELECT (COUNT(DISTINCT ?awardObj) AS ?awardsCount)
            WHERE {{
                ?player bb:playerID "{player_id}" ;
                        bb:wonAward ?awardObj .
            }}
        }}

        OPTIONAL {{
            SELECT (MAX(?salaryValue) AS ?maxSalary)
            WHERE {{
                ?player bb:playerID "{player_id}" ;
                        bb:hasSalary ?salaryObj .
                ?salaryObj bb:salary ?salaryValue .
            }}
        }}

        OPTIONAL {{
            SELECT
                (SUM(?homeRunsValue) AS ?careerHomeRuns)
                (SUM(?rbiValue) AS ?careerRBI)
                (COUNT(DISTINCT ?season) AS ?battingSeasons)
            WHERE {{
                ?player bb:playerID "{player_id}" ;
                        bb:hasBatting ?battingObj .
                OPTIONAL {{ ?battingObj bb:homeRuns ?homeRunsValue . }}
                OPTIONAL {{ ?battingObj bb:RBI ?rbiValue . }}
                OPTIONAL {{ ?battingObj bb:yearID ?season . }}
            }}
        }}
    }}
    LIMIT 1
    """

    results = run_query(query)
    if not results:
        return None

    row = results[0]

    def value_for(key, default="N/A"):
        return row.get(key, {}).get("value", default)

    return {
        "name": value_for("name"),
        "player_id": value_for("playerID"),
        "birth_year": value_for("birthYear"),
        "birth_country": value_for("birthCountry"),
        "height": value_for("height"),
        "weight": value_for("weight"),
        "awards_count": value_for("awardsCount", "0"),
        "max_salary": value_for("maxSalary", "0"),
        "career_home_runs": value_for("careerHomeRuns", "0"),
        "career_rbi": value_for("careerRBI", "0"),
        "batting_seasons": value_for("battingSeasons", "0"),
        "search_term": player_id,
    }

@lru_cache(maxsize=1)
def get_top_salaries():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    SELECT ?name ?salary ?year WHERE {
        ?p a bb:Player ;
           foaf:name ?name ;
           bb:hasSalary ?s .
        ?s bb:salary ?salary ;
           bb:yearID ?year .
    }
    ORDER BY DESC(?salary)
    LIMIT 10
    """
    return run_query(query)

@lru_cache(maxsize=1)
def get_awards_list():
    # Usamos os links completos para garantir que ele encontra os triplos
    query = """
    SELECT ?name ?award ?year
    WHERE {
        ?p <http://xmlns.com/foaf/0.1/name> ?name .
        ?p <http://baseball.ws.pt/wonAward> ?awObj .
        ?awObj <http://baseball.ws.pt/awardName> ?award ;
               <http://baseball.ws.pt/yearID> ?year .
    }
    ORDER BY DESC(?year)
    LIMIT 25
    """
    return run_query(query)


@lru_cache(maxsize=1)
def get_header_teams_graph():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?teamCode ?teamName ?franchise
    WHERE {
        ?team a bb:Team ;
              bb:yearID ?year ;
              bb:teamName ?teamName .
        FILTER(?year = 2015)
        OPTIONAL { ?team bb:teamIDBR ?teamCodeBR . }
        OPTIONAL { ?team bb:teamID ?teamCodeID . }
        OPTIONAL { ?team bb:franchID ?franchise . }
        BIND(
            COALESCE(
                ?teamCodeBR,
                ?teamCodeID,
                STRBEFORE(STRAFTER(STR(?team), "/team/"), "/")
            ) AS ?teamCode
        )
    }
    ORDER BY ?teamCode
    """

    return [
        {
            "abbr": row.get("teamCode", {}).get("value", ""),
            "name": row.get("teamName", {}).get("value", row.get("teamCode", {}).get("value", "")),
            "franchise": row.get("franchise", {}).get("value", row.get("teamCode", {}).get("value", "")),
        }
        for row in run_query(query)
        if row.get("teamCode", {}).get("value")
    ]

@lru_cache(maxsize=1024)
def get_player_graph_data(player_id):
    player_id = escape_sparql_string(player_id.strip())
    if not player_id:
        return {"nodes": [], "edges": []}

    player_query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        FILTER(?playerID = "{player_id}")
    }}
    LIMIT 1
    """

    team_query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?team ?teamName ?year ?franchise ?franchiseName
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:hasBatting ?batting .
        ?batting bb:teamOf ?team .
        OPTIONAL {{ ?team bb:teamName ?teamName . }}
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

    nodes = [{
        "data": {
            "id": player_node_id,
            "label": player_row["name"]["value"],
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
        team_year = row.get("year", {}).get("value")
        team_label = f"{team_name} ({team_year})" if team_year else team_name

        if team_node_id not in seen_nodes:
            nodes.append({
                "data": {
                    "id": team_node_id,
                    "label": team_label,
                    "type": "team",
                }
            })
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

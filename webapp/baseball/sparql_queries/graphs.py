from functools import lru_cache

from rdflib import Namespace
from rdflib.namespace import FOAF, RDF

from .base import escape_sparql_string, run_construct
from .leagues import LEAGUE_LABELS

BB = Namespace("http://baseball.ws.pt/")

NODE_TYPE_MAP = {
    BB.GraphPlayer: "player",
    BB.GraphFocusTeam: "focus-team",
    BB.GraphTeam: "team",
    BB.GraphFranchise: "franchise",
    BB.GraphAward: "award",
    BB.GraphLeague: "league",
    BB.GraphRosterPlayer: "player",
    BB.GraphTeammate: "teammate",
    BB.GraphManager: "manager",
}

NODE_TYPE_PRIORITY = {
    "player": 0,
    "focus-team": 1,
    "team": 2,
    "franchise": 3,
    "award": 4,
    "league": 5,
    "teammate": 6,
    "manager": 7,
}

EDGE_LABEL_MAP = {
    BB.playedFor: "played for",
    BB.franchiseLink: "franchise",
    BB.leagueLink: "league",
    BB.playedInLeague: "league",
    BB.rosterLink: "roster",
    BB.wonGraphAward: "won",
    BB.sharedClubhouseWith: "teammate",
    BB.managedByPerson: "managed by",
}


def _literal_value(graph, subject, *predicates):
    for predicate in predicates:
        value = graph.value(subject, predicate)
        if value is not None:
            return str(value)
    return ""


def _choose_node_type(graph, subject):
    node_types = [NODE_TYPE_MAP[obj] for obj in graph.objects(subject, RDF.type) if obj in NODE_TYPE_MAP]
    if not node_types:
        return None
    return sorted(node_types, key=lambda item: NODE_TYPE_PRIORITY.get(item, 999))[0]


def _build_node_label(graph, subject, node_type):
    if node_type in {"player", "teammate", "manager"}:
        return (
            _literal_value(graph, subject, FOAF.name, BB.nameGiven, BB.playerID)
            or "Unknown person"
        )

    if node_type in {"focus-team", "team"}:
        team_name = _literal_value(graph, subject, BB.teamName, FOAF.name, BB.teamID) or "Unknown team"
        season_year = _literal_value(graph, subject, BB.yearID)
        return f"{team_name} ({season_year})" if season_year else team_name

    if node_type == "franchise":
        return _literal_value(graph, subject, BB.franchiseName, BB.franchID) or "Unknown franchise"

    if node_type == "award":
        award_name = _literal_value(graph, subject, BB.awardName, FOAF.name) or "Award"
        award_year = _literal_value(graph, subject, BB.yearID)
        return f"{award_name} ({award_year})" if award_year else award_name

    if node_type == "league":
        league_code = _literal_value(graph, subject, BB.lgID)
        return LEAGUE_LABELS.get(league_code, league_code or "League")

    return _literal_value(graph, subject, FOAF.name) or str(subject)


def _player_graph_construct_query(player_id):
    return f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    CONSTRUCT {{
        ?player a bb:GraphPlayer ;
                bb:playerID ?playerCode ;
                foaf:name ?playerName .

        ?team a bb:GraphTeam ;
              bb:teamName ?teamName ;
              bb:teamID ?teamCode ;
              bb:yearID ?teamYear .

        ?franchise a bb:GraphFranchise ;
                   bb:franchiseName ?franchiseName ;
                   bb:franchID ?franchiseCode .

        ?award a bb:GraphAward ;
               bb:awardName ?awardName ;
               bb:yearID ?awardYear .

        ?leagueNode a bb:GraphLeague ;
                    bb:lgID ?leagueCode .

        ?teammate a bb:GraphTeammate ;
                  bb:playerID ?teammateCode ;
                  foaf:name ?teammateName ;
                  bb:sharedSeasons ?sharedSeasons .

        ?managerPlayer a bb:GraphManager ;
                       bb:playerID ?managerCode ;
                       foaf:name ?managerName .

        ?player bb:playedFor ?team .
        ?team bb:franchiseLink ?franchise .
        ?team bb:leagueLink ?leagueNode .
        ?player bb:playedInLeague ?leagueNode .
        ?player bb:wonGraphAward ?award .
        ?player bb:sharedClubhouseWith ?teammate .
        ?team bb:managedByPerson ?managerPlayer .
    }}
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerCode .
        FILTER(?playerCode = "{player_id}")
        OPTIONAL {{ ?player foaf:name ?playerName . }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?player ?team ?teamName ?teamCode ?teamYear
                                ?franchise ?franchiseName ?franchiseCode
                                ?leagueNode ?leagueCode
                WHERE {{
                    ?player bb:playerID "{player_id}" .
                    {{
                        ?player bb:hasBatting ?teamLine .
                    }}
                    UNION
                    {{
                        ?player bb:hasPitching ?teamLine .
                    }}

                    ?teamLine bb:teamOf ?team .
                    OPTIONAL {{ ?team bb:teamName ?teamName . }}
                    OPTIONAL {{ ?team bb:teamID ?teamCode . }}
                    OPTIONAL {{ ?team bb:yearID ?teamYear . }}
                    OPTIONAL {{
                        ?team bb:franchiseOf ?franchise .
                        OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}
                        OPTIONAL {{ ?franchise bb:franchID ?franchiseCode . }}
                    }}
                    OPTIONAL {{
                        ?team bb:lgID ?leagueCode .
                        BIND(IRI(CONCAT("http://baseball.ws.pt/graph/league/", STR(?leagueCode))) AS ?leagueNode)
                    }}
                }}
            }}
        }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?player ?award ?awardName ?awardYear
                WHERE {{
                    ?player bb:playerID "{player_id}" ;
                            bb:wonAward ?award .
                    OPTIONAL {{ ?award bb:awardName ?awardName . }}
                    OPTIONAL {{ ?award bb:yearID ?awardYear . }}
                }}
            }}
        }}

        OPTIONAL {{
            {{
                SELECT ?player ?teammate ?teammateCode ?teammateName ?sharedSeasons
                WHERE {{
                    {{
                        SELECT ?player ?teammate ?teammateCode ?teammateName
                               (COUNT(DISTINCT ?sharedTeam) AS ?sharedSeasons)
                        WHERE {{
                            ?player bb:playerID "{player_id}" .
                            {{
                                ?player bb:hasBatting ?playerLine .
                            }}
                            UNION
                            {{
                                ?player bb:hasPitching ?playerLine .
                            }}

                            ?playerLine bb:teamOf ?sharedTeam .

                            ?teammate a bb:Player ;
                                      bb:playerID ?teammateCode .
                            FILTER(?teammate != ?player)
                            OPTIONAL {{ ?teammate foaf:name ?teammateName . }}

                            {{
                                ?teammate bb:hasBatting ?teammateLine .
                            }}
                            UNION
                            {{
                                ?teammate bb:hasPitching ?teammateLine .
                            }}

                            ?teammateLine bb:teamOf ?sharedTeam .
                        }}
                        GROUP BY ?player ?teammate ?teammateCode ?teammateName
                        ORDER BY DESC(?sharedSeasons) ?teammateName
                    }}
                }}
            }}
        }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?team ?managerPlayer ?managerCode ?managerName
                WHERE {{
                    ?player bb:playerID "{player_id}" .
                    {{
                        ?player bb:hasBatting ?managerLine .
                    }}
                    UNION
                    {{
                        ?player bb:hasPitching ?managerLine .
                    }}

                    ?managerLine bb:teamOf ?team .

                    ?managerPlayer a bb:Player ;
                                   bb:playerID ?managerCode ;
                                   bb:isManager ?managerRole .
                    OPTIONAL {{ ?managerPlayer foaf:name ?managerName . }}

                    ?managerRole bb:managedTeam ?team .
                }}
            }}
        }}
    }}
    """


def _coerce_year(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def _team_graph_construct_query(team_code, team_year):
    return f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    CONSTRUCT {{
        ?team a bb:GraphFocusTeam ;
              bb:teamName ?teamName ;
              bb:teamID ?teamCode ;
              bb:yearID ?teamYear ;
              bb:teamIDBR ?teamCodeBr .

        ?franchise a bb:GraphFranchise ;
                   bb:franchiseName ?franchiseName ;
                   bb:franchID ?franchiseCode .

        ?leagueNode a bb:GraphLeague ;
                    bb:lgID ?leagueCode .

        ?player a bb:GraphRosterPlayer ;
                bb:playerID ?playerCode ;
                bb:bbrefID ?playerBbrefID ;
                foaf:name ?playerName .

        ?managerPlayer a bb:GraphManager ;
                       bb:playerID ?managerCode ;
                       bb:bbrefID ?managerBbrefID ;
                       foaf:name ?managerName .

        ?award a bb:GraphAward ;
               bb:awardName ?awardName ;
               bb:yearID ?awardYear .

        ?team bb:franchiseLink ?franchise .
        ?team bb:leagueLink ?leagueNode .
        ?team bb:rosterLink ?player .
        ?team bb:managedByPerson ?managerPlayer .
        ?player bb:wonGraphAward ?award .
    }}
    WHERE {{
        ?team a bb:Team ;
              bb:teamID "{team_code}" ;
              bb:yearID {team_year} .
        OPTIONAL {{ ?team bb:teamName ?teamName . }}
        OPTIONAL {{ ?team bb:teamID ?teamCode . }}
        OPTIONAL {{ ?team bb:teamIDBR ?teamCodeBr . }}
        OPTIONAL {{ ?team bb:yearID ?teamYear . }}

        OPTIONAL {{
            ?team bb:franchiseOf ?franchise .
            OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}
            OPTIONAL {{ ?franchise bb:franchID ?franchiseCode . }}
        }}

        OPTIONAL {{
            ?team bb:lgID ?leagueCode .
            BIND(IRI(CONCAT("http://baseball.ws.pt/graph/league/", STR(?leagueCode))) AS ?leagueNode)
        }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?team ?player ?playerCode ?playerBbrefID ?playerName
                WHERE {{
                    ?team a bb:Team ;
                          bb:teamID "{team_code}" ;
                          bb:yearID {team_year} .

                    ?player a bb:Player ;
                            bb:playerID ?playerCode .
                    OPTIONAL {{ ?player bb:bbrefID ?playerBbrefID . }}
                    OPTIONAL {{ ?player foaf:name ?playerName . }}

                    {{
                        ?player bb:hasBatting ?playerLine .
                    }}
                    UNION
                    {{
                        ?player bb:hasPitching ?playerLine .
                    }}

                    ?playerLine bb:teamOf ?team .
                }}
            }}
        }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?team ?managerPlayer ?managerCode ?managerBbrefID ?managerName
                WHERE {{
                    ?team a bb:Team ;
                          bb:teamID "{team_code}" ;
                          bb:yearID {team_year} .

                    ?managerPlayer a bb:Player ;
                                   bb:playerID ?managerCode ;
                                   bb:isManager ?managerRole .
                    OPTIONAL {{ ?managerPlayer bb:bbrefID ?managerBbrefID . }}
                    OPTIONAL {{ ?managerPlayer foaf:name ?managerName . }}

                    ?managerRole bb:managedTeam ?team .
                }}
            }}
        }}

        OPTIONAL {{
            {{
                SELECT DISTINCT ?player ?award ?awardName ?awardYear
                WHERE {{
                    ?team a bb:Team ;
                          bb:teamID "{team_code}" ;
                          bb:yearID {team_year} .

                    ?player a bb:Player ;
                            bb:wonAward ?award .

                    {{
                        ?player bb:hasBatting ?awardLine .
                    }}
                    UNION
                    {{
                        ?player bb:hasPitching ?awardLine .
                    }}

                    ?awardLine bb:teamOf ?team .

                    OPTIONAL {{ ?award bb:awardName ?awardName . }}
                    OPTIONAL {{ ?award bb:yearID ?awardYear . }}
                    FILTER(!BOUND(?awardYear) || ?awardYear = {team_year})
                }}
            }}
        }}
    }}
    """


def _graph_to_cytoscape(graph):
    node_map = {}
    for subject in set(graph.subjects()):
        node_type = _choose_node_type(graph, subject)
        if not node_type:
            continue

        node_id = str(subject)
        node_data = {
            "id": node_id,
            "label": _build_node_label(graph, subject, node_type),
            "type": node_type,
        }

        if node_type in {"focus-team", "team"}:
            team_code = _literal_value(graph, subject, BB.teamID)
            if team_code:
                node_data["teamID"] = team_code
            team_code_br = _literal_value(graph, subject, BB.teamIDBR)
            if team_code_br:
                node_data["teamIDBR"] = team_code_br
        elif node_type in {"player", "manager", "teammate"}:
            player_code = _literal_value(graph, subject, BB.playerID)
            if player_code:
                node_data["playerID"] = player_code
            bbref_id = _literal_value(graph, subject, BB.bbrefID)
            if bbref_id:
                node_data["bbrefID"] = bbref_id
        elif node_type == "league":
            league_code = _literal_value(graph, subject, BB.lgID)
            if league_code:
                node_data["leagueCode"] = league_code
        if node_type == "teammate":
            shared_seasons = _literal_value(graph, subject, BB.sharedSeasons)
            if shared_seasons:
                node_data["sharedSeasons"] = shared_seasons

        node_map[node_id] = {"data": node_data}

    edges = []
    seen_edges = set()
    for predicate, label in EDGE_LABEL_MAP.items():
        for source, target in graph.subject_objects(predicate):
            source_id = str(source)
            target_id = str(target)
            if source_id not in node_map or target_id not in node_map:
                continue

            edge_key = (str(predicate), source_id, target_id)
            if edge_key in seen_edges:
                continue

            edges.append(
                {
                    "data": {
                        "id": f"edge:{len(edges)}",
                        "source": source_id,
                        "target": target_id,
                        "label": label,
                    }
                }
            )
            seen_edges.add(edge_key)

    return {
        "nodes": sorted(
            node_map.values(),
            key=lambda node: (NODE_TYPE_PRIORITY.get(node["data"]["type"], 999), node["data"]["label"]),
        ),
        "edges": edges,
    }


@lru_cache(maxsize=128)
def get_player_graph_data(player_id):
    player_id = escape_sparql_string(str(player_id).strip())
    if not player_id:
        return {"nodes": [], "edges": []}

    graph = run_construct(_player_graph_construct_query(player_id))
    if not graph:
        return {"nodes": [], "edges": []}

    return _graph_to_cytoscape(graph)


@lru_cache(maxsize=128)
def get_team_graph_data(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    team_year = _coerce_year(year)
    if not team_code or team_year is None:
        return {"nodes": [], "edges": []}

    graph = run_construct(_team_graph_construct_query(team_code, team_year))
    if not graph:
        return {"nodes": [], "edges": []}

    return _graph_to_cytoscape(graph)

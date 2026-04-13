from ..sparql_queries.base import _row_int, _row_value, escape_sparql_string, run_query


def find_players_by_name(name, limit=6):
    safe_name = escape_sparql_string(str(name).strip().lower())
    if not safe_name:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name ?nameFirst ?nameLast ?birthCountry ?debut
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:debut ?debut . }}
        BIND(
            CONCAT(
                LCASE(COALESCE(STR(?name), "")), " ",
                LCASE(COALESCE(STR(?nameFirst), "")), " ",
                LCASE(COALESCE(STR(?nameLast), "")), " ",
                LCASE(COALESCE(STR(?playerID), ""))
            ) AS ?searchBlob
        )
        FILTER(CONTAINS(?searchBlob, "{safe_name}"))
    }}
    ORDER BY ?nameFirst ?nameLast ?name ?playerID
    LIMIT {max(int(limit), 1)}
    """

    players = []
    for row in run_query(query):
        players.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": (
                    " ".join(
                        part
                        for part in [_row_value(row, "nameFirst", ""), _row_value(row, "nameLast", "")]
                        if part
                    ).strip()
                    or _row_value(row, "name", "")
                ),
                "birth_country": _row_value(row, "birthCountry", ""),
                "debut": _row_value(row, "debut", ""),
            }
        )
    return players


def find_teams_by_name(name, limit=6):
    safe_name = escape_sparql_string(str(name).strip().lower())
    if not safe_name:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?franchiseId
           (SAMPLE(COALESCE(?franchiseName, ?teamName, ?franchiseId)) AS ?label)
           (SAMPLE(?league) AS ?league)
           (MAX(?year) AS ?latestYear)
    WHERE {{
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchiseId .
        OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}

        ?team a bb:Team ;
              bb:franchiseOf ?franchise ;
              bb:yearID ?year .
        OPTIONAL {{ ?team bb:teamName ?teamName . }}
        OPTIONAL {{ ?team bb:lgID ?league . }}

        FILTER(
            CONTAINS(
                LCASE(
                    CONCAT(
                        COALESCE(STR(?franchiseName), ""),
                        " ",
                        COALESCE(STR(?teamName), ""),
                        " ",
                        STR(?franchiseId)
                    )
                ),
                "{safe_name}"
            )
        )
    }}
    GROUP BY ?franchiseId
    ORDER BY ?label ?franchiseId
    LIMIT {max(int(limit), 1)}
    """

    teams = []
    for row in run_query(query):
        teams.append(
            {
                "franchise_id": _row_value(row, "franchiseId", ""),
                "name": _row_value(row, "label", ""),
                "league_code": _row_value(row, "league", ""),
                "latest_year": _row_int(row, "latestYear", 0),
            }
        )
    return teams


def get_teams_by_league_code(league_code, limit=6):
    safe_code = escape_sparql_string(str(league_code).strip().upper())
    if not safe_code:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?franchiseId
           (SAMPLE(COALESCE(?franchiseName, ?teamName, ?franchiseId)) AS ?label)
           (MIN(?year) AS ?firstYear)
           (MAX(?year) AS ?lastYear)
    WHERE {{
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchiseId .
        OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}

        ?team a bb:Team ;
              bb:franchiseOf ?franchise ;
              bb:yearID ?year ;
              bb:lgID "{safe_code}" .
        OPTIONAL {{ ?team bb:teamName ?teamName . }}
    }}
    GROUP BY ?franchiseId
    ORDER BY ?label ?franchiseId
    LIMIT {max(int(limit), 1)}
    """

    teams = []
    for row in run_query(query):
        teams.append(
            {
                "franchise_id": _row_value(row, "franchiseId", ""),
                "name": _row_value(row, "label", ""),
                "first_year": _row_int(row, "firstYear", 0),
                "last_year": _row_int(row, "lastYear", 0),
            }
        )
    return teams


def get_players_by_country(country, limit=6):
    safe_country = escape_sparql_string(str(country).strip().lower())
    if not safe_country:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name ?nameFirst ?nameLast ?birthCountry ?debut
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:birthCountry ?birthCountry .
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:debut ?debut . }}
        FILTER(LCASE(STR(?birthCountry)) = "{safe_country}")
    }}
    ORDER BY ?nameFirst ?nameLast ?name ?playerID
    LIMIT {max(int(limit), 1)}
    """

    players = []
    for row in run_query(query):
        players.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": (
                    " ".join(
                        part
                        for part in [_row_value(row, "nameFirst", ""), _row_value(row, "nameLast", "")]
                        if part
                    ).strip()
                    or _row_value(row, "name", "")
                ),
                "birth_country": _row_value(row, "birthCountry", ""),
                "debut": _row_value(row, "debut", ""),
            }
        )
    return players


def get_awards_by_year(year, limit=6):
    try:
        safe_year = int(str(year).strip())
    except (TypeError, ValueError):
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name ?nameFirst ?nameLast ?awardName ?lg
    WHERE {{
        ?player bb:playerID ?playerID ;
                bb:wonAward ?awardObj .
        OPTIONAL {{ ?player foaf:name ?name . }}
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        ?awardObj bb:awardName ?awardName ;
                  bb:yearID {safe_year} .
        OPTIONAL {{ ?awardObj bb:lgID ?lg . }}
    }}
    ORDER BY ?awardName ?nameFirst ?nameLast ?playerID
    LIMIT {max(int(limit), 1)}
    """

    awards = []
    for row in run_query(query):
        awards.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": (
                    " ".join(
                        part
                        for part in [_row_value(row, "nameFirst", ""), _row_value(row, "nameLast", "")]
                        if part
                    ).strip()
                    or _row_value(row, "name", "")
                    or _row_value(row, "playerID", "")
                ),
                "award_name": _row_value(row, "awardName", ""),
                "league_code": _row_value(row, "lg", ""),
            }
        )
    return awards


def get_salary_leaders(limit=6):
    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name ?salary ?year
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:hasSalary ?salaryObj .
        ?salaryObj bb:salary ?salary ;
                   bb:yearID ?year .
    }}
    ORDER BY DESC(?salary)
    LIMIT {max(int(limit), 1)}
    """

    leaders = []
    for row in run_query(query):
        leaders.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": _row_value(row, "name", ""),
                "salary": _row_int(row, "salary", 0),
                "year": _row_int(row, "year", 0),
            }
        )
    return leaders


from functools import lru_cache

from .base import _row_int, _row_value, escape_sparql_string, run_query
LEAGUE_LABELS = {
    "AL": "American League",
    "NL": "National League",
    "NA": "National Association",
    "AA": "American Association",
    "UA": "Union Association",
    "PL": "Players' League",
    "FL": "Federal League",
}


LEAGUE_ORDER = {
    "AL": 1,
    "NL": 2,
    "NA": 3,
    "AA": 4,
    "UA": 5,
    "PL": 6,
    "FL": 7,
}


DIVISION_LABELS = {
    "E": "East",
    "C": "Central",
    "W": "West",
}


def get_header_leagues_graph():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?league
    WHERE {
        ?team a bb:Team ;
              bb:lgID ?league .
        FILTER(STRLEN(STR(?league)) > 0)
    }
    ORDER BY ?league
    """

    leagues = []
    for row in run_query(query):
        code = _row_value(row, "league", "")
        if not code:
            continue
        leagues.append(
            {
                "code": code,
                "name": LEAGUE_LABELS.get(code, code),
                "slug": code.lower(),
                "sort_order": LEAGUE_ORDER.get(code, 999),
            }
        )

    return sorted(leagues, key=lambda league: (league["sort_order"], league["code"]))


def get_league_detail(league_code):
    league_code = escape_sparql_string(str(league_code).strip().upper())
    if not league_code:
        return None

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT
        (COUNT(DISTINCT ?team) AS ?teamSeasons)
        (COUNT(DISTINCT ?franchise) AS ?franchises)
        (COUNT(DISTINCT ?year) AS ?seasons)
        (MIN(?year) AS ?firstYear)
        (MAX(?year) AS ?lastYear)
    WHERE {{
        ?team a bb:Team ;
              bb:lgID ?lg ;
              bb:yearID ?year .
        FILTER(?lg = "{league_code}")
        OPTIONAL {{ ?team bb:franchID ?franchise . }}
    }}
    """

    results = run_query(query)
    if not results:
        return None

    row = results[0]
    team_seasons = _row_int(row, "teamSeasons", 0)
    if not team_seasons:
        return None

    return {
        "code": league_code,
        "name": LEAGUE_LABELS.get(league_code, league_code),
        "team_seasons": team_seasons,
        "franchises": _row_int(row, "franchises", 0),
        "seasons": _row_int(row, "seasons", 0),
        "first_year": _row_int(row, "firstYear", 0),
        "last_year": _row_int(row, "lastYear", 0),
    }


def get_teams_by_league(league_code):
    league_code = escape_sparql_string(str(league_code).strip().upper())
    if not league_code:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?teamName ?franchise (SAMPLE(?park) AS ?park)
           (COUNT(DISTINCT ?year) AS ?seasons)
           (MIN(?year) AS ?firstYear)
           (MAX(?year) AS ?lastYear)
    WHERE {{
        ?team a bb:Team ;
              bb:lgID ?lg ;
              bb:teamName ?teamName ;
              bb:yearID ?year .
        FILTER(?lg = "{league_code}")
        OPTIONAL {{ ?team bb:franchID ?franchise . }}
        OPTIONAL {{ ?team bb:park ?park . }}
    }}
    GROUP BY ?teamName ?franchise
    ORDER BY ?teamName ?firstYear
    """

    teams = []
    for row in run_query(query):
        teams.append(
            {
                "name": _row_value(row, "teamName", "Unknown Team"),
                "franchise": _row_value(row, "franchise", ""),
                "park": _row_value(row, "park", ""),
                "seasons": _row_int(row, "seasons", 0),
                "first_year": _row_int(row, "firstYear", 0),
                "last_year": _row_int(row, "lastYear", 0),
            }
        )
    return teams


def get_league_series_results(league_code):
    league_code = escape_sparql_string(str(league_code).strip().upper())
    if not league_code:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?round ?winnerTeamName ?loserTeamName ?wins ?losses ?ties ?lgWinner ?lgLoser
    WHERE {{
        ?series a bb:WorldSeriesResult ;
                bb:yearID ?year ;
                bb:round ?round .
                
        # --- FILTRO DE QUALIDADE ---
        # Ao remover o OPTIONAL daqui, as "Unknown Teams" desaparecem automaticamente
        ?series bb:winnerTeam ?winnerTeam .
        ?winnerTeam bb:teamName ?winnerTeamName .
                
        ?series bb:loserTeam ?loserTeam .
        ?loserTeam bb:teamName ?loserTeamName .
        # ---------------------------

        OPTIONAL {{ ?series bb:wins ?wins . }}
        OPTIONAL {{ ?series bb:losses ?losses . }}
        OPTIONAL {{ ?series bb:ties ?ties . }}
        OPTIONAL {{ ?series bb:lgIDwinner ?lgWinner . }}
        OPTIONAL {{ ?series bb:lgIDloser ?lgLoser . }}
        
        FILTER(STR(?lgWinner) = "{league_code}" || STR(?lgLoser) = "{league_code}")
    }}
    ORDER BY DESC(?year) ?round
    """

    results = []
    for row in run_query(query):
        results.append({
            "year": _row_int(row, "year", None),
            "round": _row_value(row, "round", ""),
            "winner_team_name": _row_value(row, "winnerTeamName", "Unknown Team"),
            "loser_team_name": _row_value(row, "loserTeamName", "Unknown Team"),
            "wins": _row_int(row, "wins", 0),
            "losses": _row_int(row, "losses", 0),
            "ties": _row_int(row, "ties", 0),
            "winner_league": _row_value(row, "lgWinner", ""),
            "loser_league": _row_value(row, "lgLoser", ""),
        })
    return results


def get_league_leaders(league_code, year):
    league_code = escape_sparql_string(str(league_code).strip().upper())
    try:
        year_val = int(year)
    except (ValueError, TypeError):
        year_val = None
    if not league_code or not year_val:
        return {"hr": [], "rbi": [], "assists": [], "strikeouts": []}

    def _get_top_3(stat_type_class, stat_property, has_relation):
        query = f"""
        PREFIX bb: <http://baseball.ws.pt/>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>

        SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?statValue
        WHERE {{
            ?stat a bb:{stat_type_class} ;
                  bb:lgID "{league_code}" ;
                  bb:yearID {year_val} ;
                  bb:{stat_property} ?statValue .
            ?player bb:{has_relation} ?stat ;
                    bb:playerID ?playerID .

            OPTIONAL {{ ?player foaf:name ?name . }}
            OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
            OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
            OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
        }}
        ORDER BY DESC(?statValue)
        LIMIT 3
        """
        results = []
        for row in run_query(query):
            first_name = _row_value(row, "nameFirst", "")
            last_name = _row_value(row, "nameLast", "")
            full_name = " ".join(part for part in [first_name, last_name] if part).strip()
            if not full_name:
                full_name = _row_value(row, "name", "")
            if not full_name:
                full_name = _row_value(row, "nameGiven", _row_value(row, "playerID", ""))

            results.append({
                "name": full_name,
                "player_id": _row_value(row, "playerID", ""),
                "value": _row_int(row, "statValue", 0)
            })
        return results

    return {
        "hr": _get_top_3("BattingStat", "homeRuns", "hasBatting"),
        "rbi": _get_top_3("BattingStat", "RBI", "hasBatting"),
        "assists": _get_top_3("FieldingStat", "A", "hasFielding"),
        "strikeouts": _get_top_3("PitchingStat", "SO", "hasPitching"),
    }

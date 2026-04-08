from functools import lru_cache

from .base import (
    _build_batting_rates,
    _build_pitching_rates,
    _normalize_player_id,
    _row_float,
    _row_int,
    _row_value,
    escape_sparql_string,
    run_query,
)
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


PLAYER_SORTS = {
    "name_asc": "ORDER BY ?name ?playerID",
    "name_desc": "ORDER BY DESC(?name) DESC(?playerID)",
    "debut_desc": "ORDER BY DESC(?debut) ?name ?playerID",
    "birth_year_desc": "ORDER BY DESC(?birthYear) ?name ?playerID",
}


def _player_catalog_filters(
    letter="",
    search_term="",
    birth_country="",
    bats="",
    throws="",
    debut_decade="",
    has_photo=False,
):
    filters = []

    if letter:
        safe_letter = escape_sparql_string(str(letter).strip().upper())
        if len(safe_letter) == 1 and safe_letter.isalpha():
            filters.append(f'FILTER(STRSTARTS(UCASE(STR(?name)), "{safe_letter}"))')

    if search_term:
        safe_search = escape_sparql_string(str(search_term).strip().lower())
        if safe_search:
            filters.append(f'FILTER(CONTAINS(LCASE(STR(?searchBlob)), "{safe_search}"))')

    if birth_country:
        safe_country = escape_sparql_string(str(birth_country).strip())
        if safe_country:
            filters.append(f'FILTER(?birthCountry = "{safe_country}")')

    if bats:
        safe_bats = escape_sparql_string(str(bats).strip().upper())
        if safe_bats in {"L", "R", "B"}:
            filters.append(f'FILTER(?bats = "{safe_bats}")')

    if throws:
        safe_throws = escape_sparql_string(str(throws).strip().upper())
        if safe_throws in {"L", "R"}:
            filters.append(f'FILTER(?throws = "{safe_throws}")')

    if debut_decade:
        try:
            decade = int(str(debut_decade).strip())
            filters.append(
                f'FILTER(?debut >= "{decade}-01-01"^^<http://www.w3.org/2001/XMLSchema#date> && '
                f'?debut < "{decade + 10}-01-01"^^<http://www.w3.org/2001/XMLSchema#date>)'
            )
        except ValueError:
            pass

    if has_photo:
        filters.append('FILTER(STRLEN(STR(?bbrefID)) > 0)')

    return "\n        ".join(filters)


def get_players_catalog_count(
    letter="",
    search_term="",
    birth_country="",
    bats="",
    throws="",
    debut_decade="",
    has_photo=False,
):
    filters = _player_catalog_filters(
        letter,
        search_term,
        birth_country,
        bats,
        throws,
        debut_decade,
        has_photo,
    )
    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT (COUNT(DISTINCT ?player) AS ?total)
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
        OPTIONAL {{ ?player bb:bbrefID ?bbrefID . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:bats ?bats . }}
        OPTIONAL {{ ?player bb:throws ?throws . }}
        OPTIONAL {{ ?player bb:debut ?debut . }}
        BIND(
            CONCAT(
                LCASE(COALESCE(STR(?name), "")), " ",
                LCASE(COALESCE(STR(?nameFirst), "")), " ",
                LCASE(COALESCE(STR(?nameLast), "")), " ",
                LCASE(COALESCE(STR(?nameGiven), ""))
            ) AS ?searchBlob
        )
        {filters}
    }}
    """

    results = run_query(query)
    if not results:
        return 0
    return _row_int(results[0], "total", 0)


def get_players_catalog(
    letter="",
    search_term="",
    birth_country="",
    bats="",
    throws="",
    debut_decade="",
    has_photo=False,
    sort="name_asc",
    limit=24,
    offset=0,
):
    limit = max(int(limit), 1)
    offset = max(int(offset), 0)
    filters = _player_catalog_filters(
        letter,
        search_term,
        birth_country,
        bats,
        throws,
        debut_decade,
        has_photo,
    )
    sort_clause = PLAYER_SORTS.get(sort, PLAYER_SORTS["name_asc"])

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?bbrefID ?name ?nameFirst ?nameLast ?nameGiven
           ?birthYear ?birthMonth ?birthDay ?birthCountry ?birthState ?birthCity
           ?deathYear ?deathMonth ?deathDay ?deathCountry ?deathState ?deathCity
           ?height ?weight ?bats ?throws ?debut ?finalGame
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name .
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
        OPTIONAL {{ ?player bb:bbrefID ?bbrefID . }}
        OPTIONAL {{ ?player bb:birthYear ?birthYear . }}
        OPTIONAL {{ ?player bb:birthMonth ?birthMonth . }}
        OPTIONAL {{ ?player bb:birthDay ?birthDay . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:birthState ?birthState . }}
        OPTIONAL {{ ?player bb:birthCity ?birthCity . }}
        OPTIONAL {{ ?player bb:deathYear ?deathYear . }}
        OPTIONAL {{ ?player bb:deathMonth ?deathMonth . }}
        OPTIONAL {{ ?player bb:deathDay ?deathDay . }}
        OPTIONAL {{ ?player bb:deathCountry ?deathCountry . }}
        OPTIONAL {{ ?player bb:deathState ?deathState . }}
        OPTIONAL {{ ?player bb:deathCity ?deathCity . }}
        OPTIONAL {{ ?player bb:height ?height . }}
        OPTIONAL {{ ?player bb:weight ?weight . }}
        OPTIONAL {{ ?player bb:bats ?bats . }}
        OPTIONAL {{ ?player bb:throws ?throws . }}
        OPTIONAL {{ ?player bb:debut ?debut . }}
        OPTIONAL {{ ?player bb:finalGame ?finalGame . }}
        BIND(
            CONCAT(
                LCASE(COALESCE(STR(?name), "")), " ",
                LCASE(COALESCE(STR(?nameFirst), "")), " ",
                LCASE(COALESCE(STR(?nameLast), "")), " ",
                LCASE(COALESCE(STR(?nameGiven), ""))
            ) AS ?searchBlob
        )
        {filters}
    }}
    {sort_clause}
    LIMIT {limit}
    OFFSET {offset}
    """

    players = []
    for row in run_query(query):
        first_name = _row_value(row, "nameFirst", "")
        last_name = _row_value(row, "nameLast", "")
        given_name = _row_value(row, "nameGiven", "")
        base_name = _row_value(row, "name", "Unknown Player")
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        display_name = full_name or given_name or base_name

        players.append({
            "player_id": _row_value(row, "playerID", ""),
            "bbref_id": _row_value(row, "bbrefID", ""),
            "name": display_name,
            "name_first": first_name,
            "name_last": last_name,
            "name_given": given_name,
            "birth_year": _row_value(row, "birthYear", ""),
            "birth_month": _row_value(row, "birthMonth", ""),
            "birth_day": _row_value(row, "birthDay", ""),
            "birth_country": _row_value(row, "birthCountry", ""),
            "birth_state": _row_value(row, "birthState", ""),
            "birth_city": _row_value(row, "birthCity", ""),
            "death_year": _row_value(row, "deathYear", ""),
            "death_month": _row_value(row, "deathMonth", ""),
            "death_day": _row_value(row, "deathDay", ""),
            "death_country": _row_value(row, "deathCountry", ""),
            "death_state": _row_value(row, "deathState", ""),
            "death_city": _row_value(row, "deathCity", ""),
            "height": _row_value(row, "height", ""),
            "weight": _row_value(row, "weight", ""),
            "bats": _row_value(row, "bats", ""),
            "throws": _row_value(row, "throws", ""),
            "debut": _row_value(row, "debut", ""),
            "final_game": _row_value(row, "finalGame", ""),
        })
    return players


def get_player_filter_options():
    country_query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?birthCountry
    WHERE {
        ?player a bb:Player ;
                bb:birthCountry ?birthCountry .
        FILTER(STRLEN(STR(?birthCountry)) > 0)
    }
    ORDER BY ?birthCountry
    """

    decade_query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?debut
    WHERE {
        ?player a bb:Player ;
                bb:debut ?debut .
    }
    ORDER BY ?debut
    """

    countries = [_row_value(row, "birthCountry", "") for row in run_query(country_query)]
    decades = []
    seen = set()
    for row in run_query(decade_query):
        debut = _row_value(row, "debut", "")
        try:
            year = int(str(debut)[:4])
        except (TypeError, ValueError):
            continue
        decade = year - (year % 10)
        if decade not in seen:
            seen.add(decade)
            decades.append(decade)

    return {
        "countries": [country for country in countries if country],
        "debut_decades": sorted(decades, reverse=True),
        "bats": [
            {"code": "R", "name": "Right"},
            {"code": "L", "name": "Left"},
            {"code": "B", "name": "Switch"},
        ],
        "throws": [
            {"code": "R", "name": "Right"},
            {"code": "L", "name": "Left"},
        ],
        "sorts": [
            {"code": "name_asc", "name": "Name A-Z"},
            {"code": "name_desc", "name": "Name Z-A"},
            {"code": "debut_desc", "name": "Latest debut"},
            {"code": "birth_year_desc", "name": "Youngest first"},
        ],
    }


def get_player_summary(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return None

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?name ?nameFirst ?nameLast ?nameGiven ?playerID ?bbrefID
           ?birthYear ?birthMonth ?birthDay ?birthCountry ?birthState ?birthCity
           ?deathYear ?deathMonth ?deathDay ?deathCountry ?deathState ?deathCity
           ?height ?weight ?bats ?throws ?debut ?finalGame
           ?awardsCount ?maxSalary ?careerHomeRuns ?careerRBI ?battingSeasons
    WHERE {{
        ?player a bb:Player ;
                foaf:name ?name ;
                bb:playerID ?playerID .
        FILTER(?playerID = "{player_id}")

        OPTIONAL {{ ?player bb:bbrefID ?bbrefID . }}
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
        OPTIONAL {{ ?player bb:birthYear ?birthYear . }}
        OPTIONAL {{ ?player bb:birthMonth ?birthMonth . }}
        OPTIONAL {{ ?player bb:birthDay ?birthDay . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:birthState ?birthState . }}
        OPTIONAL {{ ?player bb:birthCity ?birthCity . }}
        OPTIONAL {{ ?player bb:deathYear ?deathYear . }}
        OPTIONAL {{ ?player bb:deathMonth ?deathMonth . }}
        OPTIONAL {{ ?player bb:deathDay ?deathDay . }}
        OPTIONAL {{ ?player bb:deathCountry ?deathCountry . }}
        OPTIONAL {{ ?player bb:deathState ?deathState . }}
        OPTIONAL {{ ?player bb:deathCity ?deathCity . }}
        OPTIONAL {{ ?player bb:height ?height . }}
        OPTIONAL {{ ?player bb:weight ?weight . }}
        OPTIONAL {{ ?player bb:bats ?bats . }}
        OPTIONAL {{ ?player bb:throws ?throws . }}
        OPTIONAL {{ ?player bb:debut ?debut . }}
        OPTIONAL {{ ?player bb:finalGame ?finalGame . }}

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
                ?battingObj a bb:BattingStat .
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

    first_name = value_for("nameFirst", "")
    last_name = value_for("nameLast", "")
    given_name = value_for("nameGiven", "")
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if not full_name:
        full_name = value_for("name", "")
    if not full_name:
        full_name = given_name or value_for("playerID")

    return {
        "name": full_name,
        "name_first": first_name,
        "name_last": last_name,
        "name_given": given_name,
        "player_id": value_for("playerID"),
        "bbref_id": value_for("bbrefID", ""),
        "birth_year": value_for("birthYear"),
        "birth_month": value_for("birthMonth", ""),
        "birth_day": value_for("birthDay", ""),
        "birth_country": value_for("birthCountry"),
        "birth_state": value_for("birthState", ""),
        "birth_city": value_for("birthCity", ""),
        "death_year": value_for("deathYear", ""),
        "death_month": value_for("deathMonth", ""),
        "death_day": value_for("deathDay", ""),
        "death_country": value_for("deathCountry", ""),
        "death_state": value_for("deathState", ""),
        "death_city": value_for("deathCity", ""),
        "height": value_for("height"),
        "weight": value_for("weight"),
        "bats": value_for("bats"),
        "throws": value_for("throws"),
        "debut": value_for("debut"),
        "final_game": value_for("finalGame"),
        "awards_count": value_for("awardsCount", "0"),
        "max_salary": value_for("maxSalary", "0"),
        "career_home_runs": value_for("careerHomeRuns", "0"),
        "career_rbi": value_for("careerRBI", "0"),
        "batting_seasons": value_for("battingSeasons", "0"),
        "search_term": player_id,
    }


def get_player_batting_seasons(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?teamName ?lg
           ?gamesValue ?atBatsValue ?runsValue ?hitsValue ?doublesValue ?triplesValue
           ?homeRunsValue ?rbiValue ?stolenBasesValue ?walksValue ?strikeoutsValue
           ?hitByPitchValue ?sacrificeFliesValue
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:hasBatting ?batting .
        ?batting a bb:BattingStat ;
                 bb:yearID ?year .
        OPTIONAL {{ ?batting bb:G ?gamesValue . }}
        OPTIONAL {{ ?batting bb:AB ?atBatsValue . }}
        OPTIONAL {{ ?batting bb:R ?runsValue . }}
        OPTIONAL {{ ?batting bb:H ?hitsValue . }}
        OPTIONAL {{ ?batting <http://baseball.ws.pt/2B> ?doublesValue . }}
        OPTIONAL {{ ?batting <http://baseball.ws.pt/3B> ?triplesValue . }}
        OPTIONAL {{ ?batting bb:homeRuns ?homeRunsValue . }}
        OPTIONAL {{ ?batting bb:RBI ?rbiValue . }}
        OPTIONAL {{ ?batting bb:SB ?stolenBasesValue . }}
        OPTIONAL {{ ?batting bb:BB ?walksValue . }}
        OPTIONAL {{ ?batting bb:SO ?strikeoutsValue . }}
        OPTIONAL {{ ?batting bb:HBP ?hitByPitchValue . }}
        OPTIONAL {{ ?batting bb:SF ?sacrificeFliesValue . }}
        OPTIONAL {{
            ?batting bb:teamOf ?team .
            OPTIONAL {{ ?team bb:teamName ?teamName . }}
        }}
        OPTIONAL {{ ?batting bb:lgID ?lg . }}
    }}
    ORDER BY ?year
    """

    seasons = {}
    for row in run_query(query):
        year = _row_int(row, "year")
        if not year:
            continue

        season = seasons.setdefault(
            year,
            {
                "year": year,
                "teams": set(),
                "leagues": set(),
                "games": 0,
                "at_bats": 0,
                "runs": 0,
                "hits": 0,
                "doubles": 0,
                "triples": 0,
                "home_runs": 0,
                "rbi": 0,
                "stolen_bases": 0,
                "walks": 0,
                "strikeouts": 0,
                "hit_by_pitch": 0,
                "sacrifice_flies": 0,
            },
        )

        team_name = _row_value(row, "teamName")
        if team_name:
            season["teams"].add(team_name)
        lg = _row_value(row, "lg")
        if lg:
            season["leagues"].add(lg)

        season["games"] += _row_int(row, "gamesValue")
        season["at_bats"] += _row_int(row, "atBatsValue")
        season["runs"] += _row_int(row, "runsValue")
        season["hits"] += _row_int(row, "hitsValue")
        season["doubles"] += _row_int(row, "doublesValue")
        season["triples"] += _row_int(row, "triplesValue")
        season["home_runs"] += _row_int(row, "homeRunsValue")
        season["rbi"] += _row_int(row, "rbiValue")
        season["stolen_bases"] += _row_int(row, "stolenBasesValue")
        season["walks"] += _row_int(row, "walksValue")
        season["strikeouts"] += _row_int(row, "strikeoutsValue")
        season["hit_by_pitch"] += _row_int(row, "hitByPitchValue")
        season["sacrifice_flies"] += _row_int(row, "sacrificeFliesValue")

    lines = []
    for season in sorted(seasons.values(), key=lambda item: item["year"]):
        season["teams"] = sorted(season["teams"])
        season["leagues"] = sorted(season["leagues"])
        season["team_label"] = ", ".join(season["teams"]) if season["teams"] else "Unknown team"
        season["league_label"] = ", ".join(season["leagues"]) if season["leagues"] else "N/A"
        season["seasons"] = 1
        lines.append(_build_batting_rates(season))
    return lines


def get_player_batting_summary(player_id):
    seasons = get_player_batting_seasons(player_id)
    summary = {
        "games": 0,
        "at_bats": 0,
        "runs": 0,
        "hits": 0,
        "doubles": 0,
        "triples": 0,
        "home_runs": 0,
        "rbi": 0,
        "stolen_bases": 0,
        "walks": 0,
        "strikeouts": 0,
        "hit_by_pitch": 0,
        "sacrifice_flies": 0,
        "seasons": len(seasons),
    }

    for season in seasons:
        for key in (
            "games",
            "at_bats",
            "runs",
            "hits",
            "doubles",
            "triples",
            "home_runs",
            "rbi",
            "stolen_bases",
            "walks",
            "strikeouts",
            "hit_by_pitch",
            "sacrifice_flies",
        ):
            summary[key] += season.get(key, 0)

    return _build_batting_rates(summary)


def get_player_pitching_seasons(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?teamName ?lg
           ?winsValue ?lossesValue ?gamesValue ?gamesStartedValue ?savesValue
           ?inningsOutsValue ?earnedRunsValue ?strikeoutsValue ?eraValue
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:hasPitching ?pitching .
        ?pitching a bb:PitchingStat ;
                  bb:yearID ?year .
        OPTIONAL {{ ?pitching bb:W ?winsValue . }}
        OPTIONAL {{ ?pitching bb:L ?lossesValue . }}
        OPTIONAL {{ ?pitching bb:G ?gamesValue . }}
        OPTIONAL {{ ?pitching bb:GS ?gamesStartedValue . }}
        OPTIONAL {{ ?pitching bb:SV ?savesValue . }}
        OPTIONAL {{ ?pitching bb:IPouts ?inningsOutsValue . }}
        OPTIONAL {{ ?pitching bb:ER ?earnedRunsValue . }}
        OPTIONAL {{ ?pitching bb:SO ?strikeoutsValue . }}
        OPTIONAL {{ ?pitching bb:ERA ?eraValue . }}
        OPTIONAL {{
            ?pitching bb:teamOf ?team .
            OPTIONAL {{ ?team bb:teamName ?teamName . }}
        }}
        OPTIONAL {{ ?pitching bb:lgID ?lg . }}
    }}
    ORDER BY ?year
    """

    seasons = {}
    for row in run_query(query):
        year = _row_int(row, "year")
        if not year:
            continue

        season = seasons.setdefault(
            year,
            {
                "year": year,
                "teams": set(),
                "leagues": set(),
                "wins": 0,
                "losses": 0,
                "games": 0,
                "games_started": 0,
                "saves": 0,
                "innings_outs": 0,
                "earned_runs": 0,
                "strikeouts": 0,
                "_has_wins": False,
                "_has_losses": False,
                "_has_games": False,
                "_has_games_started": False,
                "_has_saves": False,
                "_has_innings_outs": False,
                "_has_earned_runs": False,
                "_has_strikeouts": False,
                "_era_values": [],
            },
        )

        team_name = _row_value(row, "teamName")
        if team_name:
            season["teams"].add(team_name)
        lg = _row_value(row, "lg")
        if lg:
            season["leagues"].add(lg)

        if _row_value(row, "winsValue") not in (None, ""):
            season["wins"] += _row_int(row, "winsValue")
            season["_has_wins"] = True
        if _row_value(row, "lossesValue") not in (None, ""):
            season["losses"] += _row_int(row, "lossesValue")
            season["_has_losses"] = True
        if _row_value(row, "gamesValue") not in (None, ""):
            season["games"] += _row_int(row, "gamesValue")
            season["_has_games"] = True
        if _row_value(row, "gamesStartedValue") not in (None, ""):
            season["games_started"] += _row_int(row, "gamesStartedValue")
            season["_has_games_started"] = True
        if _row_value(row, "savesValue") not in (None, ""):
            season["saves"] += _row_int(row, "savesValue")
            season["_has_saves"] = True
        if _row_value(row, "inningsOutsValue") not in (None, ""):
            season["innings_outs"] += _row_int(row, "inningsOutsValue")
            season["_has_innings_outs"] = True
        if _row_value(row, "earnedRunsValue") not in (None, ""):
            season["earned_runs"] += _row_int(row, "earnedRunsValue")
            season["_has_earned_runs"] = True
        if _row_value(row, "strikeoutsValue") not in (None, ""):
            season["strikeouts"] += _row_int(row, "strikeoutsValue")
            season["_has_strikeouts"] = True
        if _row_value(row, "eraValue") not in (None, ""):
            season["_era_values"].append(_row_float(row, "eraValue", None))

    lines = []
    for season in sorted(seasons.values(), key=lambda item: item["year"]):
        season["teams"] = sorted(season["teams"])
        season["leagues"] = sorted(season["leagues"])
        season["team_label"] = ", ".join(season["teams"]) if season["teams"] else "Unknown team"
        season["league_label"] = ", ".join(season["leagues"]) if season["leagues"] else "N/A"
        season["seasons"] = 1
        if not season["_has_wins"]:
            season["wins"] = None
        if not season["_has_losses"]:
            season["losses"] = None
        if not season["_has_games"]:
            season["games"] = None
        if not season["_has_games_started"]:
            season["games_started"] = None
        if not season["_has_saves"]:
            season["saves"] = None
        if not season["_has_innings_outs"]:
            season["innings_outs"] = None
        if not season["_has_earned_runs"]:
            season["earned_runs"] = None
        if not season["_has_strikeouts"]:
            season["strikeouts"] = None
        if season["innings_outs"] not in (None, 0) and season["earned_runs"] is not None:
            season["era"] = (season["earned_runs"] * 27) / season["innings_outs"]
        else:
            era_values = [value for value in season["_era_values"] if value is not None]
            season["era"] = (sum(era_values) / len(era_values)) if era_values else None
        lines.append(_build_pitching_rates(season))
    return lines


def get_player_pitching_summary(player_id):
    seasons = get_player_pitching_seasons(player_id)
    summary = {"seasons": len(seasons)}

    for key in (
        "wins",
        "losses",
        "games",
        "games_started",
        "saves",
        "innings_outs",
        "earned_runs",
        "strikeouts",
    ):
        values = [season.get(key) for season in seasons if season.get(key) is not None]
        summary[key] = sum(values) if values else None

    if summary["innings_outs"] not in (None, 0) and summary["earned_runs"] is not None:
        summary["era"] = (summary["earned_runs"] * 27) / summary["innings_outs"]
    else:
        era_values = [season.get("era") for season in seasons if season.get("era") is not None]
        summary["era"] = (sum(era_values) / len(era_values)) if era_values else None
    return _build_pitching_rates(summary)


def get_player_award_history(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?awardName ?lg ?notes
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:wonAward ?award .
        OPTIONAL {{ ?award bb:yearID ?year . }}
        OPTIONAL {{ ?award bb:awardName ?awardName . }}
        OPTIONAL {{ ?award bb:lgID ?lg . }}
        OPTIONAL {{ ?award bb:notes ?notes . }}
    }}
    ORDER BY ?year ?awardName
    """

    return [
        {
            "year": _row_int(row, "year", None),
            "award_name": _row_value(row, "awardName", "Award"),
            "league": _row_value(row, "lg", ""),
            "notes": _row_value(row, "notes", ""),
        }
        for row in run_query(query)
    ]


def get_player_allstar_history(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?gameID ?startingPos ?teamName
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:playedInAllStar ?appearance .
        OPTIONAL {{ ?appearance bb:yearID ?year . }}
        OPTIONAL {{ ?appearance bb:gameID ?gameID . }}
        OPTIONAL {{ ?appearance bb:startingPos ?startingPos . }}
        OPTIONAL {{
            ?appearance bb:teamOf ?team .
            OPTIONAL {{ ?team bb:teamName ?teamName . }}
        }}
    }}
    ORDER BY ?year
    """

    return [
        {
            "year": _row_int(row, "year", None),
            "game_id": _row_value(row, "gameID", ""),
            "starting_position": _row_int(row, "startingPos", None),
            "team_name": _row_value(row, "teamName", ""),
        }
        for row in run_query(query)
    ]


def get_player_hall_of_fame(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return {"inducted": False, "inducted_year": None, "vote_count": 0}

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?inducted ?votes ?needed
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:hallOfFameVote ?vote .
        OPTIONAL {{ ?vote bb:yearID ?year . }}
        OPTIONAL {{ ?vote bb:inducted ?inducted . }}
        OPTIONAL {{ ?vote bb:votes ?votes . }}
        OPTIONAL {{ ?vote bb:needed ?needed . }}
    }}
    ORDER BY ?year
    """

    history = []
    inducted_year = None
    for row in run_query(query):
        inducted = str(_row_value(row, "inducted", "")).lower() == "true"
        year = _row_int(row, "year", None)
        if inducted and inducted_year is None:
            inducted_year = year
        history.append(
            {
                "year": year,
                "inducted": inducted,
                "votes": _row_int(row, "votes", None),
                "needed": _row_int(row, "needed", None),
            }
        )

    return {
        "inducted": inducted_year is not None,
        "inducted_year": inducted_year,
        "vote_count": len(history),
        "history": history,
    }


def get_player_salary_history(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?salaryValue ?teamName
    WHERE {{
        ?player bb:playerID "{player_id}" ;
                bb:hasSalary ?salaryObj .
        ?salaryObj bb:salary ?salaryValue .
        OPTIONAL {{ ?salaryObj bb:yearID ?year . }}
        OPTIONAL {{
            ?salaryObj bb:teamOf ?team .
            OPTIONAL {{ ?team bb:teamName ?teamName . }}
        }}
    }}
    ORDER BY DESC(?salaryValue) DESC(?year)
    """

    return [
        {
            "year": _row_int(row, "year", None),
            "salary": _row_int(row, "salaryValue"),
            "team_name": _row_value(row, "teamName", ""),
        }
        for row in run_query(query)
    ]


def get_player_team_history(player_id):
    player_id = _normalize_player_id(player_id)
    if not player_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT DISTINCT ?year ?teamName ?franchiseName ?lg
    WHERE {{
        ?player bb:playerID "{player_id}" .
        {{
            ?player bb:hasBatting ?season .
            ?season a bb:BattingStat .
        }}
        UNION
        {{
            ?player bb:hasPitching ?season .
            ?season a bb:PitchingStat .
        }}
        ?season bb:yearID ?year .
        OPTIONAL {{ ?season bb:lgID ?lg . }}
        OPTIONAL {{
            ?season bb:teamOf ?team .
            OPTIONAL {{ ?team bb:teamName ?teamName . }}
            OPTIONAL {{
                ?team bb:franchiseOf ?franchise .
                OPTIONAL {{ ?franchise bb:franchiseName ?franchiseName . }}
            }}
        }}
    }}
    ORDER BY ?year ?teamName
    """

    return [
        {
            "year": _row_int(row, "year", None),
            "team_name": _row_value(row, "teamName", ""),
            "franchise_name": _row_value(row, "franchiseName", ""),
            "league": _row_value(row, "lg", ""),
        }
        for row in run_query(query)
    ]

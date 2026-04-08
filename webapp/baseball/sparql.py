from functools import lru_cache

from SPARQLWrapper import SPARQLWrapper, JSON

# URL do teu repositório no GraphDB
ENDPOINT = "http://localhost:7200/repositories/baseball"
QUIZ_YEAR_MIN = 2000

def run_query(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]


def _row_value(row, key, default=None):
    return row.get(key, {}).get("value", default)


def _row_int(row, key, default=0):
    value = _row_value(row, key)
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _row_float(row, key, default=0.0):
    value = _row_value(row, key)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _row_bool(row, key, default=False):
    value = _row_value(row, key)
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes"}


def _normalize_player_id(player_id):
    return escape_sparql_string(str(player_id).strip())


def _outs_to_decimal_innings(ip_outs):
    if ip_outs is None:
        return None
    if not ip_outs:
        return 0.0
    whole = ip_outs // 3
    remainder = ip_outs % 3
    return float(f"{whole}.{remainder}")


def _build_batting_rates(line):
    at_bats = line.get("at_bats", 0)
    hits = line.get("hits", 0)
    doubles = line.get("doubles", 0)
    triples = line.get("triples", 0)
    home_runs = line.get("home_runs", 0)
    walks = line.get("walks", 0)
    hit_by_pitch = line.get("hit_by_pitch", 0)
    sacrifice_flies = line.get("sacrifice_flies", 0)
    strikeouts = line.get("strikeouts", 0)
    seasons = line.get("seasons", 0)

    singles = max(hits - doubles - triples - home_runs, 0)
    total_bases = singles + (2 * doubles) + (3 * triples) + (4 * home_runs)

    line["avg"] = (hits / at_bats) if at_bats else None
    obp_denom = at_bats + walks + hit_by_pitch + sacrifice_flies
    line["obp"] = ((hits + walks + hit_by_pitch) / obp_denom) if obp_denom else None
    line["slg"] = (total_bases / at_bats) if at_bats else None
    line["ops"] = (
        (line["obp"] + line["slg"])
        if line["obp"] is not None and line["slg"] is not None
        else None
    )
    line["bb_k_ratio"] = (walks / strikeouts) if strikeouts else None
    line["hr_per_season"] = (home_runs / seasons) if seasons else None
    return line


def _build_pitching_rates(line):
    innings_outs = line.get("innings_outs", 0)
    earned_runs = line.get("earned_runs", 0)
    line["innings_pitched"] = _outs_to_decimal_innings(innings_outs)
    if line.get("era") is None:
        line["era"] = ((earned_runs * 27) / innings_outs) if innings_outs else None
    return line

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


@lru_cache(maxsize=256)
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


@lru_cache(maxsize=256)
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


@lru_cache(maxsize=1)
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

@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1024)
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


@lru_cache(maxsize=1)
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


@lru_cache(maxsize=32)
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


@lru_cache(maxsize=32)
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


@lru_cache(maxsize=1)
def get_team_franchise_catalog():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?franchiseId ?franchiseName ?active
           ?year ?teamName ?teamId ?teamIdBr ?league ?division ?rank
           ?park ?attendance ?wins ?losses
           ?divisionWinner ?wildCardWinner ?leagueWinner ?worldSeriesWinner
    WHERE {
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchiseId .
        OPTIONAL { ?franchise bb:franchiseName ?franchiseName . }
        OPTIONAL { ?franchise bb:active ?active . }

        ?team a bb:Team ;
              bb:franchiseOf ?franchise ;
              bb:yearID ?year .

        OPTIONAL { ?team bb:teamName ?teamName . }
        OPTIONAL { ?team bb:teamID ?teamId . }
        OPTIONAL { ?team bb:teamIDBR ?teamIdBr . }
        OPTIONAL { ?team bb:lgID ?league . }
        OPTIONAL { ?team bb:divID ?division . }
        OPTIONAL { ?team bb:Rank ?rank . }
        OPTIONAL { ?team bb:park ?park . }
        OPTIONAL { ?team bb:attendance ?attendance . }
        OPTIONAL { ?team bb:W ?wins . }
        OPTIONAL { ?team bb:L ?losses . }
        OPTIONAL { ?team bb:DivWin ?divisionWinner . }
        OPTIONAL { ?team bb:WCWin ?wildCardWinner . }
        OPTIONAL { ?team bb:LgWin ?leagueWinner . }
        OPTIONAL { ?team bb:WSWin ?worldSeriesWinner . }
    }
    ORDER BY ?franchiseId DESC(?year)
    """

    teams_map = {}
    for row in run_query(query):
        franchise_id = _row_value(row, "franchiseId", "")
        if not franchise_id:
            continue
        year = _row_int(row, "year", 0)
        entry = teams_map.setdefault(
            franchise_id,
            {
                "franchise_id": franchise_id,
                "name": _row_value(row, "franchiseName", "") or franchise_id,
                "active": _row_bool(row, "active", False),
                "season_count": 0,
                "first_year": year,
                "last_year": year,
                "latest_year": 0,
                "latest_team_name": "",
                "latest_team_id": "",
                "latest_team_id_br": "",
                "latest_league_code": "",
                "latest_division_code": "",
                "latest_rank": None,
                "latest_park": "",
                "latest_attendance": None,
                "latest_wins": None,
                "latest_losses": None,
                "latest_division_winner": False,
                "latest_wild_card_winner": False,
                "latest_league_winner": False,
                "latest_world_series_winner": False,
            },
        )
        entry["season_count"] += 1
        if year:
            entry["first_year"] = min(entry["first_year"], year) if entry["first_year"] else year
            entry["last_year"] = max(entry["last_year"], year)
        if year >= entry["latest_year"]:
            entry["latest_year"] = year
            entry["latest_team_name"] = _row_value(row, "teamName", "") or entry["name"]
            entry["latest_team_id"] = _row_value(row, "teamId", "")
            entry["latest_team_id_br"] = _row_value(row, "teamIdBr", "")
            entry["latest_league_code"] = _row_value(row, "league", "")
            entry["latest_division_code"] = _row_value(row, "division", "")
            entry["latest_rank"] = _row_int(row, "rank", None)
            entry["latest_park"] = _row_value(row, "park", "")
            entry["latest_attendance"] = _row_int(row, "attendance", None)
            entry["latest_wins"] = _row_int(row, "wins", None)
            entry["latest_losses"] = _row_int(row, "losses", None)
            entry["latest_division_winner"] = _row_bool(row, "divisionWinner", False)
            entry["latest_wild_card_winner"] = _row_bool(row, "wildCardWinner", False)
            entry["latest_league_winner"] = _row_bool(row, "leagueWinner", False)
            entry["latest_world_series_winner"] = _row_bool(row, "worldSeriesWinner", False)

    return sorted(
        teams_map.values(),
        key=lambda team: (
            0 if team["active"] else 1,
            team["name"],
            team["franchise_id"],
        ),
    )


@lru_cache(maxsize=128)
def get_team_history(franchise_id):
    franchise_id = escape_sparql_string(str(franchise_id).strip().upper())
    if not franchise_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?teamName ?teamId ?teamIdBr ?league ?division ?rank ?games ?homeGames
           ?wins ?losses ?divisionWinner ?wildCardWinner ?leagueWinner ?worldSeriesWinner
           ?runs ?atBats ?hits ?doubles ?triples ?homeRuns ?walks ?strikeouts ?stolenBases
           ?caughtStealing ?hitByPitch ?sacrificeFlies ?runsAllowed ?earnedRuns ?era
           ?completeGames ?shutouts ?saves ?inningsOuts ?hitsAllowed ?homeRunsAllowed
           ?walksAllowed ?strikeoutsPitching ?errors ?doublePlays ?fieldPct ?park
           ?attendance ?bpf ?ppf
    WHERE {{
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchiseId .
        FILTER(?franchiseId = "{franchise_id}")

        ?team a bb:Team ;
              bb:franchiseOf ?franchise ;
              bb:yearID ?year .

        OPTIONAL {{ ?team bb:teamName ?teamName . }}
        OPTIONAL {{ ?team bb:teamID ?teamId . }}
        OPTIONAL {{ ?team bb:teamIDBR ?teamIdBr . }}
        OPTIONAL {{ ?team bb:lgID ?league . }}
        OPTIONAL {{ ?team bb:divID ?division . }}
        OPTIONAL {{ ?team bb:Rank ?rank . }}
        OPTIONAL {{ ?team bb:G ?games . }}
        OPTIONAL {{ ?team bb:Ghome ?homeGames . }}
        OPTIONAL {{ ?team bb:W ?wins . }}
        OPTIONAL {{ ?team bb:L ?losses . }}
        OPTIONAL {{ ?team bb:DivWin ?divisionWinner . }}
        OPTIONAL {{ ?team bb:WCWin ?wildCardWinner . }}
        OPTIONAL {{ ?team bb:LgWin ?leagueWinner . }}
        OPTIONAL {{ ?team bb:WSWin ?worldSeriesWinner . }}
        OPTIONAL {{ ?team bb:R ?runs . }}
        OPTIONAL {{ ?team bb:AB ?atBats . }}
        OPTIONAL {{ ?team bb:H ?hits . }}
        OPTIONAL {{ ?team bb:2B ?doubles . }}
        OPTIONAL {{ ?team bb:3B ?triples . }}
        OPTIONAL {{ ?team bb:HR ?homeRuns . }}
        OPTIONAL {{ ?team bb:BB ?walks . }}
        OPTIONAL {{ ?team bb:SO ?strikeouts . }}
        OPTIONAL {{ ?team bb:SB ?stolenBases . }}
        OPTIONAL {{ ?team bb:CS ?caughtStealing . }}
        OPTIONAL {{ ?team bb:HBP ?hitByPitch . }}
        OPTIONAL {{ ?team bb:SF ?sacrificeFlies . }}
        OPTIONAL {{ ?team bb:RA ?runsAllowed . }}
        OPTIONAL {{ ?team bb:ER ?earnedRuns . }}
        OPTIONAL {{ ?team bb:ERA ?era . }}
        OPTIONAL {{ ?team bb:CG ?completeGames . }}
        OPTIONAL {{ ?team bb:SHO ?shutouts . }}
        OPTIONAL {{ ?team bb:SV ?saves . }}
        OPTIONAL {{ ?team bb:IPouts ?inningsOuts . }}
        OPTIONAL {{ ?team bb:HA ?hitsAllowed . }}
        OPTIONAL {{ ?team bb:HRA ?homeRunsAllowed . }}
        OPTIONAL {{ ?team bb:BBA ?walksAllowed . }}
        OPTIONAL {{ ?team bb:SOA ?strikeoutsPitching . }}
        OPTIONAL {{ ?team bb:E ?errors . }}
        OPTIONAL {{ ?team bb:DP ?doublePlays . }}
        OPTIONAL {{ ?team bb:FP ?fieldPct . }}
        OPTIONAL {{ ?team bb:park ?park . }}
        OPTIONAL {{ ?team bb:attendance ?attendance . }}
        OPTIONAL {{ ?team bb:BPF ?bpf . }}
        OPTIONAL {{ ?team bb:PPF ?ppf . }}
    }}
    ORDER BY DESC(?year)
    """

    seasons = []
    for row in run_query(query):
        season = {
            "year": _row_int(row, "year", 0),
            "team_name": _row_value(row, "teamName", "Unknown Team"),
            "team_id": _row_value(row, "teamId", ""),
            "team_id_br": _row_value(row, "teamIdBr", ""),
            "league_code": _row_value(row, "league", ""),
            "division_code": _row_value(row, "division", ""),
            "rank": _row_int(row, "rank", None),
            "games": _row_int(row, "games", 0),
            "home_games": _row_int(row, "homeGames", 0),
            "wins": _row_int(row, "wins", 0),
            "losses": _row_int(row, "losses", 0),
            "division_winner": _row_bool(row, "divisionWinner", False),
            "wild_card_winner": _row_bool(row, "wildCardWinner", False),
            "league_winner": _row_bool(row, "leagueWinner", False),
            "world_series_winner": _row_bool(row, "worldSeriesWinner", False),
            "runs": _row_int(row, "runs", 0),
            "at_bats": _row_int(row, "atBats", 0),
            "hits": _row_int(row, "hits", 0),
            "doubles": _row_int(row, "doubles", 0),
            "triples": _row_int(row, "triples", 0),
            "home_runs": _row_int(row, "homeRuns", 0),
            "walks": _row_int(row, "walks", 0),
            "strikeouts": _row_int(row, "strikeouts", 0),
            "stolen_bases": _row_int(row, "stolenBases", 0),
            "caught_stealing": _row_int(row, "caughtStealing", 0),
            "hit_by_pitch": _row_int(row, "hitByPitch", 0),
            "sacrifice_flies": _row_int(row, "sacrificeFlies", 0),
            "runs_allowed": _row_int(row, "runsAllowed", 0),
            "earned_runs": _row_int(row, "earnedRuns", 0),
            "era": _row_float(row, "era", None),
            "complete_games": _row_int(row, "completeGames", 0),
            "shutouts": _row_int(row, "shutouts", 0),
            "saves": _row_int(row, "saves", 0),
            "innings_outs": _row_int(row, "inningsOuts", 0),
            "hits_allowed": _row_int(row, "hitsAllowed", 0),
            "home_runs_allowed": _row_int(row, "homeRunsAllowed", 0),
            "walks_allowed": _row_int(row, "walksAllowed", 0),
            "strikeouts_pitching": _row_int(row, "strikeoutsPitching", 0),
            "errors": _row_int(row, "errors", 0),
            "double_plays": _row_int(row, "doublePlays", 0),
            "fielding_pct": _row_float(row, "fieldPct", None),
            "park": _row_value(row, "park", ""),
            "attendance": _row_int(row, "attendance", None),
            "bpf": _row_int(row, "bpf", None),
            "ppf": _row_int(row, "ppf", None),
            "seasons": 1,
        }
        season["win_pct"] = (season["wins"] / season["games"]) if season["games"] else None
        season["run_diff"] = season["runs"] - season["runs_allowed"]
        season["attendance_per_game"] = (
            season["attendance"] / season["home_games"]
            if season["attendance"] and season["home_games"]
            else None
        )
        _build_batting_rates(season)
        _build_pitching_rates(season)
        seasons.append(season)

    return seasons


@lru_cache(maxsize=128)
def get_team_postseason_history(franchise_id):
    franchise_id = escape_sparql_string(str(franchise_id).strip().upper())
    if not franchise_id:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?round ?wins ?losses ?ties ?result ?teamName ?opponentName ?league ?opponentLeague
    WHERE {{
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchiseId .
        FILTER(?franchiseId = "{franchise_id}")

        ?series a bb:WorldSeriesResult ;
                bb:yearID ?year ;
                bb:round ?round ;
                bb:winnerTeam ?winnerTeam ;
                bb:loserTeam ?loserTeam .

        ?winnerTeam bb:franchiseOf ?winnerFranchise ;
                    bb:teamName ?winnerTeamName .
        ?loserTeam bb:franchiseOf ?loserFranchise ;
                   bb:teamName ?loserTeamName .

        OPTIONAL {{ ?winnerTeam bb:lgID ?winnerLeague . }}
        OPTIONAL {{ ?loserTeam bb:lgID ?loserLeague . }}
        OPTIONAL {{ ?series bb:wins ?wins . }}
        OPTIONAL {{ ?series bb:losses ?losses . }}
        OPTIONAL {{ ?series bb:ties ?ties . }}

        FILTER(?winnerFranchise = ?franchise || ?loserFranchise = ?franchise)

        BIND(IF(?winnerFranchise = ?franchise, "Won", "Lost") AS ?result)
        BIND(IF(?winnerFranchise = ?franchise, ?winnerTeamName, ?loserTeamName) AS ?teamName)
        BIND(IF(?winnerFranchise = ?franchise, ?loserTeamName, ?winnerTeamName) AS ?opponentName)
        BIND(IF(?winnerFranchise = ?franchise, ?winnerLeague, ?loserLeague) AS ?league)
        BIND(IF(?winnerFranchise = ?franchise, ?loserLeague, ?winnerLeague) AS ?opponentLeague)
    }}
    ORDER BY DESC(?year) ?round
    """

    results = []
    for row in run_query(query):
        results.append(
            {
                "year": _row_int(row, "year", None),
                "round": _row_value(row, "round", ""),
                "result": _row_value(row, "result", ""),
                "team_name": _row_value(row, "teamName", ""),
                "opponent_name": _row_value(row, "opponentName", ""),
                "wins": _row_int(row, "wins", 0),
                "losses": _row_int(row, "losses", 0),
                "ties": _row_int(row, "ties", 0),
                "league_code": _row_value(row, "league", ""),
                "opponent_league_code": _row_value(row, "opponentLeague", ""),
            }
        )
    return results


def _coerce_year_value(year):
    try:
        return int(str(year).strip())
    except (TypeError, ValueError, AttributeError):
        return None


@lru_cache(maxsize=512)
def get_team_batting_roster(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    year_value = _coerce_year_value(year)
    if not team_code or year_value is None:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name
           (SUM(?games) AS ?games)
           (SUM(?atBats) AS ?atBats)
           (SUM(?hits) AS ?hits)
           (SUM(?doubles) AS ?doubles)
           (SUM(?triples) AS ?triples)
           (SUM(?homeRuns) AS ?homeRuns)
           (SUM(?runsBattedIn) AS ?runsBattedIn)
           (SUM(?stolenBases) AS ?stolenBases)
           (SUM(?walks) AS ?walks)
           (SUM(?strikeouts) AS ?strikeouts)
           (SUM(?hitByPitch) AS ?hitByPitch)
           (SUM(?sacrificeFlies) AS ?sacrificeFlies)
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:hasBatting ?batting .
        ?batting bb:teamOf ?team .
        ?team bb:teamID ?teamId ;
              bb:yearID ?teamYear .
        FILTER(?teamId = "{team_code}" && ?teamYear = {year_value})

        OPTIONAL {{ ?batting bb:G ?games . }}
        OPTIONAL {{ ?batting bb:AB ?atBats . }}
        OPTIONAL {{ ?batting bb:H ?hits . }}
        OPTIONAL {{ ?batting bb:2B ?doubles . }}
        OPTIONAL {{ ?batting bb:3B ?triples . }}
        OPTIONAL {{ ?batting bb:HR ?homeRuns . }}
        OPTIONAL {{ ?batting bb:RBI ?runsBattedIn . }}
        OPTIONAL {{ ?batting bb:SB ?stolenBases . }}
        OPTIONAL {{ ?batting bb:BB ?walks . }}
        OPTIONAL {{ ?batting bb:SO ?strikeouts . }}
        OPTIONAL {{ ?batting bb:HBP ?hitByPitch . }}
        OPTIONAL {{ ?batting bb:SF ?sacrificeFlies . }}
    }}
    GROUP BY ?playerID ?name
    ORDER BY DESC(?atBats) DESC(?homeRuns) ?name
    """

    hitters = []
    for row in run_query(query):
        hitter = {
            "player_id": _row_value(row, "playerID", ""),
            "name": _row_value(row, "name", "Unknown Player"),
            "games": _row_int(row, "games", 0),
            "at_bats": _row_int(row, "atBats", 0),
            "hits": _row_int(row, "hits", 0),
            "doubles": _row_int(row, "doubles", 0),
            "triples": _row_int(row, "triples", 0),
            "home_runs": _row_int(row, "homeRuns", 0),
            "rbi": _row_int(row, "runsBattedIn", 0),
            "stolen_bases": _row_int(row, "stolenBases", 0),
            "walks": _row_int(row, "walks", 0),
            "strikeouts": _row_int(row, "strikeouts", 0),
            "hit_by_pitch": _row_int(row, "hitByPitch", 0),
            "sacrifice_flies": _row_int(row, "sacrificeFlies", 0),
            "seasons": 1,
        }
        hitter["plate_appearances"] = (
            hitter["at_bats"]
            + hitter["walks"]
            + hitter["hit_by_pitch"]
            + hitter["sacrifice_flies"]
        )
        _build_batting_rates(hitter)
        hitters.append(hitter)

    return hitters


@lru_cache(maxsize=512)
def get_team_pitching_roster(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    year_value = _coerce_year_value(year)
    if not team_code or year_value is None:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?name
           (SUM(?games) AS ?games)
           (SUM(?wins) AS ?wins)
           (SUM(?losses) AS ?losses)
           (SUM(?gamesStarted) AS ?gamesStarted)
           (SUM(?saves) AS ?saves)
           (SUM(?strikeouts) AS ?strikeouts)
           (SUM(?inningsOuts) AS ?inningsOuts)
           (SUM(?earnedRuns) AS ?earnedRuns)
           (AVG(?eraValue) AS ?era)
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:hasPitching ?pitching .
        ?pitching bb:teamOf ?team .
        ?team bb:teamID ?teamId ;
              bb:yearID ?teamYear .
        FILTER(?teamId = "{team_code}" && ?teamYear = {year_value})

        OPTIONAL {{ ?pitching bb:G ?games . }}
        OPTIONAL {{ ?pitching bb:W ?wins . }}
        OPTIONAL {{ ?pitching bb:L ?losses . }}
        OPTIONAL {{ ?pitching bb:GS ?gamesStarted . }}
        OPTIONAL {{ ?pitching bb:SV ?saves . }}
        OPTIONAL {{ ?pitching bb:SO ?strikeouts . }}
        OPTIONAL {{ ?pitching bb:IPouts ?inningsOuts . }}
        OPTIONAL {{ ?pitching bb:ER ?earnedRuns . }}
        OPTIONAL {{ ?pitching bb:ERA ?eraValue . }}
    }}
    GROUP BY ?playerID ?name
    ORDER BY DESC(?inningsOuts) DESC(?strikeouts) ?name
    """

    pitchers = []
    for row in run_query(query):
        pitcher = {
            "player_id": _row_value(row, "playerID", ""),
            "name": _row_value(row, "name", "Unknown Player"),
            "games": _row_int(row, "games", 0),
            "wins": _row_int(row, "wins", 0),
            "losses": _row_int(row, "losses", 0),
            "games_started": _row_int(row, "gamesStarted", 0),
            "saves": _row_int(row, "saves", 0),
            "strikeouts": _row_int(row, "strikeouts", 0),
            "innings_outs": _row_int(row, "inningsOuts", 0),
            "earned_runs": _row_int(row, "earnedRuns", 0),
            "era": _row_float(row, "era", None),
        }
        _build_pitching_rates(pitcher)
        pitchers.append(pitcher)

    return pitchers


@lru_cache(maxsize=512)
def get_team_managers(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    year_value = _coerce_year_value(year)
    if not team_code or year_value is None:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT DISTINCT ?playerID ?name ?wins ?losses ?rank ?inseason
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                bb:isManager ?manager .
        OPTIONAL {{ ?player foaf:name ?name . }}

        ?manager bb:managedTeam ?team .
        ?team bb:teamID ?teamId ;
              bb:yearID ?teamYear .
        FILTER(?teamId = "{team_code}" && ?teamYear = {year_value})

        OPTIONAL {{ ?manager bb:wins ?wins . }}
        OPTIONAL {{ ?manager bb:losses ?losses . }}
        OPTIONAL {{ ?manager bb:rank ?rank . }}
        OPTIONAL {{ ?manager bb:inseason ?inseason . }}
    }}
    ORDER BY ?inseason ?rank ?name
    """

    managers = []
    for row in run_query(query):
        managers.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": _row_value(row, "name", "Unknown Manager"),
                "wins": _row_int(row, "wins", 0),
                "losses": _row_int(row, "losses", 0),
                "rank": _row_int(row, "rank", None),
                "inseason": _row_value(row, "inseason", ""),
            }
        )
    return managers


@lru_cache(maxsize=512)
def get_team_all_stars(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    year_value = _coerce_year_value(year)
    if not team_code or year_value is None:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT DISTINCT ?playerID ?name
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:playedInAllStar ?appearance .
        ?appearance bb:teamOf ?team .
        ?team bb:teamID ?teamId ;
              bb:yearID ?teamYear .
        FILTER(?teamId = "{team_code}" && ?teamYear = {year_value})
    }}
    ORDER BY ?name
    """

    return [
        {
            "player_id": _row_value(row, "playerID", ""),
            "name": _row_value(row, "name", "Unknown Player"),
        }
        for row in run_query(query)
    ]


@lru_cache(maxsize=512)
def get_team_awards(team_code, year):
    team_code = escape_sparql_string(str(team_code).strip().upper())
    year_value = _coerce_year_value(year)
    if not team_code or year_value is None:
        return []

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT DISTINCT ?playerID ?name ?awardName
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                foaf:name ?name ;
                bb:wonAward ?award .
        ?award bb:yearID ?awardYear ;
               bb:awardName ?awardName .
        FILTER(?awardYear = {year_value})

        {{
            ?player bb:hasBatting ?line .
            ?line bb:teamOf ?team .
        }}
        UNION
        {{
            ?player bb:hasPitching ?line .
            ?line bb:teamOf ?team .
        }}

        ?team bb:teamID ?teamId ;
              bb:yearID ?teamYear .
        FILTER(?teamId = "{team_code}" && ?teamYear = {year_value})
    }}
    ORDER BY ?awardName ?name
    """

    awards = []
    for row in run_query(query):
        awards.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": _row_value(row, "name", "Unknown Player"),
                "award_name": _row_value(row, "awardName", "Award"),
            }
        )
    return awards

@lru_cache(maxsize=1024)
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

@lru_cache(maxsize=32)
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


@lru_cache(maxsize=128)
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


def _player_name_from_row(row):
    first_name = _row_value(row, "nameFirst", "")
    last_name = _row_value(row, "nameLast", "")
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if not full_name:
        full_name = _row_value(row, "name", "")
    if not full_name:
        full_name = _row_value(row, "nameGiven", _row_value(row, "playerID", ""))
    return full_name


@lru_cache(maxsize=8)
def get_quiz_leaderboard_bank(stat_key):
    stat_map = {
        "home_runs": ("BattingStat", "homeRuns", "hasBatting"),
        "rbi": ("BattingStat", "RBI", "hasBatting"),
        "strikeouts": ("PitchingStat", "SO", "hasPitching"),
    }
    stat_config = stat_map.get(str(stat_key).strip())
    if not stat_config:
        return []

    stat_type_class, stat_property, has_relation = stat_config
    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?lg ?year ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?statValue
    WHERE {{
        ?stat a bb:{stat_type_class} ;
              bb:lgID ?lg ;
              bb:yearID ?year ;
              bb:{stat_property} ?statValue .
        ?player bb:{has_relation} ?stat ;
                bb:playerID ?playerID .
        FILTER(?year >= {QUIZ_YEAR_MIN})
        FILTER(?lg IN ("AL", "NL"))

        OPTIONAL {{ ?player foaf:name ?name . }}
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
    }}
    ORDER BY ?lg DESC(?year) DESC(?statValue) ?playerID
    """

    grouped = {}
    for row in run_query(query):
        league_code = _row_value(row, "lg", "").strip().upper()
        year = _row_int(row, "year", None)
        player_id = _row_value(row, "playerID", "").strip()
        if not league_code or not year or not player_id:
            continue

        key = (league_code, year)
        bucket = grouped.setdefault(
            key,
            {
                "league_code": league_code,
                "year": year,
                "leaders": [],
                "_seen_players": set(),
            },
        )
        if player_id in bucket["_seen_players"]:
            continue

        bucket["_seen_players"].add(player_id)
        bucket["leaders"].append(
            {
                "player_id": player_id,
                "name": _player_name_from_row(row),
                "value": _row_int(row, "statValue", 0),
            }
        )

    records = []
    for item in grouped.values():
        if len(item["leaders"]) < 4:
            continue
        leaders = item["leaders"][:4]
        records.append(
            {
                "league_code": item["league_code"],
                "year": item["year"],
                "leaders": leaders,
            }
        )

    return sorted(records, key=lambda item: (item["league_code"], -item["year"]))


@lru_cache(maxsize=1)
def get_quiz_salary_bank():
    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?year ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?salary
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                bb:hasSalary ?salaryObj .
        ?salaryObj bb:salary ?salary ;
                   bb:yearID ?year .
        FILTER(?year >= {QUIZ_YEAR_MIN})

        OPTIONAL {{ ?player foaf:name ?name . }}
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
    }}
    ORDER BY DESC(?year) DESC(?salary) ?playerID
    """

    grouped = {}
    for row in run_query(query):
        year = _row_int(row, "year", None)
        player_id = _row_value(row, "playerID", "").strip()
        if not year or not player_id:
            continue

        bucket = grouped.setdefault(
            year,
            {
                "year": year,
                "leaders": [],
                "_seen_players": set(),
            },
        )
        if player_id in bucket["_seen_players"]:
            continue

        bucket["_seen_players"].add(player_id)
        bucket["leaders"].append(
            {
                "player_id": player_id,
                "name": _player_name_from_row(row),
                "value": _row_int(row, "salary", 0),
            }
        )

    records = []
    for item in grouped.values():
        if len(item["leaders"]) < 4:
            continue
        records.append(
            {
                "year": item["year"],
                "leaders": item["leaders"][:4],
            }
        )

    return sorted(records, key=lambda item: -item["year"])


@lru_cache(maxsize=1)
def get_quiz_award_bank():
    supported_awards = [
        "Most Valuable Player",
        "Cy Young Award",
        "Rookie of the Year",
        "Hank Aaron Award",
        "Comeback Player of the Year",
    ]
    award_filter = ", ".join(f'"{escape_sparql_string(name)}"' for name in supported_awards)

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?awardName ?lg ?year ?playerID ?nameFirst ?nameLast ?nameGiven ?name
    WHERE {{
        ?player a bb:Player ;
                bb:playerID ?playerID ;
                bb:wonAward ?award .
        ?award bb:awardName ?awardName ;
               bb:yearID ?year .
        FILTER(?year >= {QUIZ_YEAR_MIN})
        FILTER(?awardName IN ({award_filter}))
        OPTIONAL {{ ?award bb:lgID ?lg . }}
        OPTIONAL {{ ?player foaf:name ?name . }}
        OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
        OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
        OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
    }}
    ORDER BY ?awardName ?lg ?year ?playerID
    """

    grouped = {}
    for row in run_query(query):
        award_name = _row_value(row, "awardName", "").strip()
        league_code = _row_value(row, "lg", "").strip().upper() or "ML"
        year = _row_int(row, "year", None)
        player_id = _row_value(row, "playerID", "").strip()
        if not award_name or not year or not player_id:
            continue

        group_key = (award_name, league_code)
        bucket = grouped.setdefault(
            group_key,
            {
                "award_name": award_name,
                "league_code": league_code,
                "winners_by_year": {},
            },
        )
        winners = bucket["winners_by_year"].setdefault(year, [])
        winners.append(
            {
                "year": year,
                "player_id": player_id,
                "name": _player_name_from_row(row),
            }
        )

    records = []
    for item in grouped.values():
        winners = []
        for year, year_winners in item["winners_by_year"].items():
            unique_by_player = []
            seen_players = set()
            for winner in year_winners:
                if winner["player_id"] in seen_players:
                    continue
                seen_players.add(winner["player_id"])
                unique_by_player.append(winner)
            if len(unique_by_player) == 1:
                winners.append(unique_by_player[0])

        if len(winners) < 4:
            continue

        records.append(
            {
                "award_name": item["award_name"],
                "league_code": item["league_code"],
                "winners": sorted(winners, key=lambda winner: winner["year"]),
            }
        )

    return sorted(records, key=lambda item: (item["award_name"], item["league_code"]))

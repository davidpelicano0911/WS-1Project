from functools import lru_cache

from .base import _row_int, _row_value, escape_sparql_string, run_ask, run_query
from .leagues import LEAGUE_LABELS


QUIZ_YEAR_MIN = 2000


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
                "league_label": LEAGUE_LABELS.get(league_code, league_code),
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
        records.append(
            {
                "league_code": item["league_code"],
                "league_label": item["league_label"],
                "year": item["year"],
                "leaders": item["leaders"][:4],
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


def ask_quiz_leaderboard_answer(stat_key, league_code, year, player_id):
    stat_map = {
        "home_runs": ("BattingStat", "homeRuns", "hasBatting"),
        "rbi": ("BattingStat", "RBI", "hasBatting"),
        "strikeouts": ("PitchingStat", "SO", "hasPitching"),
    }
    stat_config = stat_map.get(str(stat_key).strip())
    if not stat_config:
        return False

    stat_type_class, stat_property, has_relation = stat_config
    safe_league = escape_sparql_string(str(league_code).strip().upper())
    safe_player = escape_sparql_string(str(player_id).strip())
    try:
        year_value = int(year)
    except (TypeError, ValueError):
        return False

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    ASK {{
        ?player bb:playerID "{safe_player}" ;
                bb:{has_relation} ?stat .
        ?stat a bb:{stat_type_class} ;
              bb:lgID "{safe_league}" ;
              bb:yearID {year_value} ;
              bb:{stat_property} ?statValue .

        FILTER NOT EXISTS {{
            ?otherStat a bb:{stat_type_class} ;
                      bb:lgID "{safe_league}" ;
                      bb:yearID {year_value} ;
                      bb:{stat_property} ?otherValue .
            FILTER(?otherValue > ?statValue)
        }}
    }}
    """
    return run_ask(query)


def ask_quiz_salary_answer(year, player_id):
    safe_player = escape_sparql_string(str(player_id).strip())
    try:
        year_value = int(year)
    except (TypeError, ValueError):
        return False

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    ASK {{
        ?player a bb:Player ;
                bb:playerID "{safe_player}" ;
                bb:hasSalary ?salaryObj .
        ?salaryObj bb:salary ?salaryValue ;
                   bb:yearID {year_value} .

        FILTER NOT EXISTS {{
            ?otherPlayer a bb:Player ;
                         bb:hasSalary ?otherSalaryObj .
            ?otherSalaryObj bb:salary ?otherValue ;
                            bb:yearID {year_value} .
            FILTER(?otherValue > ?salaryValue)
        }}
    }}
    """
    return run_ask(query)


def ask_quiz_award_answer(award_name, league_code, year, player_id):
    safe_award = escape_sparql_string(str(award_name).strip())
    safe_league = escape_sparql_string(str(league_code or "").strip().upper())
    safe_player = escape_sparql_string(str(player_id).strip())
    try:
        year_value = int(year)
    except (TypeError, ValueError):
        return False

    league_filter = ""
    if safe_league and safe_league != "ML":
        league_filter = f'?award bb:lgID "{safe_league}" .'

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>

    ASK {{
        ?player a bb:Player ;
                bb:playerID "{safe_player}" ;
                bb:wonAward ?award .
        ?award bb:awardName "{safe_award}" ;
               bb:yearID {year_value} .
        {league_filter}
    }}
    """
    return run_ask(query)

from functools import lru_cache

from .base import (
    _build_batting_rates,
    _build_pitching_rates,
    _coerce_year_value,
    _row_bool,
    _row_float,
    _row_int,
    _row_value,
    escape_sparql_string,
    run_query,
)
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

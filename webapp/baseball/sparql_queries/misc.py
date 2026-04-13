from functools import lru_cache

from .base import _row_float, _row_int, _row_value, run_query


def _year_sort_key(entry):
    year = entry.get("year")
    return (year is None, year if year is not None else 0)


def _option_sort_key(entry):
    return ((entry.get("name") or entry.get("award_name") or entry.get("league") or "").lower(),)


def _build_awards_payload(rows):
    awards = []
    for row in rows:
        first_name = _row_value(row, "nameFirst", "")
        last_name = _row_value(row, "nameLast", "")
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()

        if not full_name:
            full_name = _row_value(row, "name", "")
        if not full_name:
            full_name = _row_value(row, "nameGiven", "")
        if not full_name:
            full_name = _row_value(row, "playerID", "Unknown player")

        awards.append(
            {
                "player_id": _row_value(row, "playerID", ""),
                "name": full_name,
                "award_name": _row_value(row, "awardName", "Award"),
                "year": _row_int(row, "year", 0),
                "league": _row_value(row, "lg", ""),
            }
        )
    return awards

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
def get_salary_trends():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year
           (SUM(?salary) AS ?totalSalary)
           (AVG(?salary) AS ?avgSalary)
           (MAX(?salary) AS ?maxSalary)
           (COUNT(DISTINCT ?playerID) AS ?paidPlayers)
    WHERE {
        ?player bb:playerID ?playerID ;
                bb:hasSalary ?salaryObj .
        ?salaryObj bb:salary ?salary ;
                   bb:yearID ?year .
    }
    GROUP BY ?year
    ORDER BY ?year
    """
    rows = []
    for row in run_query(query):
        year = _row_int(row, "year", None)
        if year is None:
            continue
        rows.append(
            {
                "year": year,
                "total_salary": _row_int(row, "totalSalary", 0),
                "avg_salary": round(_row_float(row, "avgSalary", 0.0), 2),
                "max_salary": _row_int(row, "maxSalary", 0),
                "paid_players": _row_int(row, "paidPlayers", 0),
            }
        )
    return sorted(rows, key=_year_sort_key)


@lru_cache(maxsize=1)
def get_franchise_history():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?franchID ?franchName ?year ?wins ?losses ?runs ?runsAllowed
    WHERE {
        ?franchise a bb:Franchise ;
                   bb:franchID ?franchID .
        OPTIONAL { ?franchise bb:franchiseName ?franchName . }

        ?team a bb:Team ;
              bb:franchiseOf ?franchise ;
              bb:yearID ?year .

        OPTIONAL { ?team bb:W ?wins . }
        OPTIONAL { ?team bb:L ?losses . }
        OPTIONAL { ?team bb:R ?runs . }
        OPTIONAL { ?team bb:RA ?runsAllowed . }
    }
    ORDER BY ?franchName ?franchID ?year
    """
    history = []
    for row in run_query(query):
        franch_id = _row_value(row, "franchID", "")
        year = _row_int(row, "year", None)
        if not franch_id or year is None:
            continue

        wins = _row_int(row, "wins", 0)
        losses = _row_int(row, "losses", 0)
        total_games = wins + losses
        runs = _row_int(row, "runs", 0)
        runs_allowed = _row_int(row, "runsAllowed", 0)

        history.append(
            {
                "franch_id": franch_id,
                "franch_name": _row_value(row, "franchName", "") or franch_id,
                "year": year,
                "wins": wins,
                "losses": losses,
                "runs": runs,
                "runs_allowed": runs_allowed,
                "win_pct": round((wins / total_games), 3) if total_games else 0.0,
                "run_diff": runs - runs_allowed,
            }
        )
    return sorted(history, key=lambda entry: ((entry["franch_name"] or entry["franch_id"]).lower(), entry["franch_id"], entry["year"]))


@lru_cache(maxsize=1)
def get_franchise_options():
    options = {}
    for row in get_franchise_history():
        options.setdefault(
            row["franch_id"],
            {"franch_id": row["franch_id"], "name": row["franch_name"] or row["franch_id"]},
        )
    return sorted(options.values(), key=_option_sort_key)


@lru_cache(maxsize=1)
def get_awards_timeline():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year ?awardName ?league (COUNT(DISTINCT ?awardObj) AS ?awardCount)
    WHERE {
        ?player bb:wonAward ?awardObj .
        ?awardObj bb:awardName ?awardName ;
                  bb:yearID ?year .
        OPTIONAL { ?awardObj bb:lgID ?league . }
    }
    GROUP BY ?year ?awardName ?league
    ORDER BY ?year ?awardName ?league
    """
    timeline = []
    for row in run_query(query):
        year = _row_int(row, "year", None)
        award_name = _row_value(row, "awardName", "")
        if year is None or not award_name:
            continue
        timeline.append(
            {
                "year": year,
                "award_name": award_name,
                "league": _row_value(row, "league", ""),
                "count": _row_int(row, "awardCount", 0),
            }
        )
    return sorted(timeline, key=lambda entry: (entry["year"], entry["award_name"].lower(), entry["league"]))


@lru_cache(maxsize=1)
def get_award_options():
    options = {row["award_name"] for row in get_awards_timeline() if row.get("award_name")}
    return [{"award_name": award_name} for award_name in sorted(options, key=str.lower)]


@lru_cache(maxsize=1)
def get_award_league_options():
    leagues = {row["league"] for row in get_awards_timeline() if row.get("league")}
    return [{"league": league} for league in sorted(leagues, key=str.upper)]


@lru_cache(maxsize=1)
def get_hall_of_fame_timeline():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?year
           (COUNT(DISTINCT ?hof) AS ?inductedCount)
           (SUM(?votes) AS ?totalVotes)
           (SUM(?ballots) AS ?totalBallots)
    WHERE {
        ?hof a bb:HallOfFameVote ;
             bb:inducted true ;
             bb:yearID ?year ;
             bb:votes ?votes ;
             bb:ballots ?ballots .
    }
    GROUP BY ?year
    ORDER BY ?year
    """
    rows = []
    for row in run_query(query):
        year = _row_int(row, "year", None)
        if year is None:
            continue
        total_ballots = _row_int(row, "totalBallots", 0)
        total_votes = _row_int(row, "totalVotes", 0)
        rows.append(
            {
                "year": year,
                "inducted_count": _row_int(row, "inductedCount", 0),
                "vote_pct": round((total_votes / total_ballots) * 100, 1) if total_ballots else None,
            }
        )
    return sorted(rows, key=_year_sort_key)


@lru_cache(maxsize=1)
def get_awards_list():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?awardName ?year ?lg
    WHERE {
        ?p bb:wonAward ?awObj .
        ?p bb:playerID ?playerID .
        ?awObj bb:awardName ?awardName ;
              bb:yearID ?year .

        OPTIONAL { ?p foaf:name ?name . }
        OPTIONAL { ?p bb:nameFirst ?nameFirst . }
        OPTIONAL { ?p bb:nameLast ?nameLast . }
        OPTIONAL { ?p bb:nameGiven ?nameGiven . }
        OPTIONAL { ?awObj bb:lgID ?lg . }
    }
    ORDER BY DESC(?year)
    LIMIT 25
    """
    return _build_awards_payload(run_query(query))


@lru_cache(maxsize=1)
def get_awards_catalog():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?awardName ?year ?lg
    WHERE {
        ?p bb:wonAward ?awObj .
        ?p bb:playerID ?playerID .
        ?awObj bb:awardName ?awardName ;
              bb:yearID ?year .

        OPTIONAL { ?p foaf:name ?name . }
        OPTIONAL { ?p bb:nameFirst ?nameFirst . }
        OPTIONAL { ?p bb:nameLast ?nameLast . }
        OPTIONAL { ?p bb:nameGiven ?nameGiven . }
        OPTIONAL { ?awObj bb:lgID ?lg . }
    }
    ORDER BY DESC(?year) ?awardName ?playerID
    """
    return _build_awards_payload(run_query(query))


@lru_cache(maxsize=1)
def get_award_year_options():
    years = {row["year"] for row in get_awards_timeline() if row.get("year")}
    return [{"year": year} for year in sorted(years, reverse=True)]


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

@lru_cache(maxsize=1)
def get_hall_of_fame_members():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name ?yearID ?votedBy ?ballots ?votes ?needed ?category
    WHERE {
        ?hof a bb:HallOfFameVote ;
             bb:inducted true ;
             bb:yearID ?yearID ;
             bb:category ?category .
             
        # Para esta lista, queremos focar em quem tem dados de votos
        ?hof bb:votes ?votes .
        ?hof bb:ballots ?ballots .

        OPTIONAL { ?hof bb:votedBy ?votedBy . }
        OPTIONAL { ?hof bb:needed ?needed . }

        ?player bb:hallOfFameVote ?hof ;
                bb:playerID ?playerID .

        OPTIONAL { ?player foaf:name ?name . }
        OPTIONAL { ?player bb:nameFirst ?nameFirst . }
        OPTIONAL { ?player bb:nameLast ?nameLast . }
        OPTIONAL { ?player bb:nameGiven ?nameGiven . }
    }
    """
    results = []
    seen = set()
    
    for row in run_query(query):
        pid = _row_value(row, "playerID")
        year = _row_value(row, "yearID")
        key = f"{pid}_{year}"
        
        if key in seen:
            continue
        seen.add(key)
        
        # Construção do nome
        first_name = _row_value(row, "nameFirst", "")
        last_name = _row_value(row, "nameLast", "")
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        
        if not full_name:
            full_name = _row_value(row, "name", "")
        if not full_name:
            full_name = _row_value(row, "nameGiven", pid)
            
        # Dados numéricos
        votes = _row_int(row, "votes", 0)
        ballots = _row_int(row, "ballots", 0)
        needed = _row_int(row, "needed", 0)
        
        # Cálculo da percentagem (apenas se ballots > 0)
        if ballots > 0:
            percent_val = (votes / ballots * 100)
            
            results.append({
                "player_id": pid,
                "name": full_name,
                "year": _row_int(row, "yearID", 0),
                "voted_by": _row_value(row, "votedBy", "-"),
                "category": _row_value(row, "category", "-"),
                "votes_str": f"{votes} / {ballots}",
                "needed_str": str(needed) if needed > 0 else "-",
                "percent": f"{percent_val:.1f}%",
                "sort_percent": percent_val
            })
        
    # Ordenação: Primeiro os que tiveram maior % de votos, depois por ano mais recente
    results.sort(key=lambda x: (x["sort_percent"], x["year"]), reverse=True)
    
    return results

@lru_cache(maxsize=1)
def get_managers_list():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name (SUM(?w) AS ?totalWins) (SUM(?l) AS ?totalLosses) (MIN(?yearID) AS ?firstYear) (MAX(?yearID) AS ?lastYear)
    WHERE {
        ?mgr a bb:Manager ;
             bb:yearID ?yearID ;
             bb:wins ?w ;
             bb:losses ?l .
             
        ?player bb:isManager ?mgr ;
                bb:playerID ?playerID .

        OPTIONAL { ?player foaf:name ?name . }
        OPTIONAL { ?player bb:nameFirst ?nameFirst . }
        OPTIONAL { ?player bb:nameLast ?nameLast . }
        OPTIONAL { ?player bb:nameGiven ?nameGiven . }
    }
    GROUP BY ?playerID ?nameFirst ?nameLast ?nameGiven ?name
    HAVING (SUM(?w) > 0)
    ORDER BY DESC(?totalWins)
    LIMIT 200
    """
    results = []
    for row in run_query(query):
        pid = _row_value(row, "playerID")
        
        first_name = _row_value(row, "nameFirst", "")
        last_name = _row_value(row, "nameLast", "")
        full_name = " ".join(part for part in [first_name, last_name] if part).strip()
        if not full_name:
            full_name = _row_value(row, "name", "")
        if not full_name:
            full_name = _row_value(row, "nameGiven", pid)
            
        wins = _row_int(row, "totalWins", 0)
        losses = _row_int(row, "totalLosses", 0)
        total_games = wins + losses
        win_pct = (wins / total_games) if total_games > 0 else 0
        
        results.append({
            "player_id": pid,
            "name": full_name,
            "wins": wins,
            "losses": losses,
            "win_pct": f"{win_pct:.3f}",
            "first_year": _row_int(row, "firstYear", 0),
            "last_year": _row_int(row, "lastYear", 0)
        })
    return results

@lru_cache(maxsize=1)
def get_global_player_leaders():
    # Helper for top sum queries
    def _get_top_sum(stat_type_class, stat_property, has_relation):
        query = f"""
        PREFIX bb: <http://baseball.ws.pt/>
        PREFIX foaf: <http://xmlns.com/foaf/0.1/>

        SELECT ?playerID ?nameFirst ?nameLast ?nameGiven ?name (SUM(?statValue) AS ?totalStat)
        WHERE {{
            ?stat a bb:{stat_type_class} ;
                  bb:{stat_property} ?statValue .
            ?player bb:{has_relation} ?stat ;
                    bb:playerID ?playerID .

            OPTIONAL {{ ?player foaf:name ?name . }}
            OPTIONAL {{ ?player bb:nameFirst ?nameFirst . }}
            OPTIONAL {{ ?player bb:nameLast ?nameLast . }}
            OPTIONAL {{ ?player bb:nameGiven ?nameGiven . }}
        }}
        GROUP BY ?playerID ?nameFirst ?nameLast ?nameGiven ?name
        ORDER BY DESC(?totalStat)
        LIMIT 5
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
                "value": _row_int(row, "totalStat", 0)
            })
        return results

    return {
        "hr": _get_top_sum("BattingStat", "homeRuns", "hasBatting"),
        "rbi": _get_top_sum("BattingStat", "RBI", "hasBatting"),
        "strikeouts": _get_top_sum("PitchingStat", "SO", "hasPitching"),
    }

@lru_cache(maxsize=1)
def get_global_team_leaders():
    query = """
    PREFIX bb: <http://baseball.ws.pt/>

    SELECT ?franchID ?franchName (SUM(?w) AS ?totalWins)
    WHERE {
        ?team a bb:Team ;
              bb:franchID ?franchID ;
              bb:W ?w .
        ?franch a bb:Franchise ;
                bb:franchID ?franchID ;
                bb:franchiseName ?franchName .
    }
    GROUP BY ?franchID ?franchName
    ORDER BY DESC(?totalWins)
    LIMIT 10
    """
    results = []
    for row in run_query(query):
        results.append({
            "franch_id": _row_value(row, "franchID", ""),
            "name": _row_value(row, "franchName", ""),
            "wins": _row_int(row, "totalWins", 0)
        })
    return results

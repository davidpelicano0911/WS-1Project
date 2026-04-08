from functools import lru_cache

from .base import _row_value, run_query
from ..sparql import _row_int

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

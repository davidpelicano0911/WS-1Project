from functools import lru_cache

from .base import _row_value, run_query
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

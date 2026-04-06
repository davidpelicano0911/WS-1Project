from functools import lru_cache

from SPARQLWrapper import SPARQLWrapper, JSON

# URL do teu repositório no GraphDB
ENDPOINT = "http://localhost:7200/repositories/baseball"

def run_query(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]

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

@lru_cache(maxsize=1024)
def get_player_summary(player_id):
    player_id = escape_sparql_string(player_id.strip())
    if not player_id:
        return None

    query = f"""
    PREFIX bb: <http://baseball.ws.pt/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?name ?playerID ?birthYear ?birthCountry ?height ?weight ?awardsCount ?maxSalary ?careerHomeRuns ?careerRBI ?battingSeasons
    WHERE {{
        ?player a bb:Player ;
                foaf:name ?name ;
                bb:playerID ?playerID .
        FILTER(?playerID = "{player_id}")

        OPTIONAL {{ ?player bb:birthYear ?birthYear . }}
        OPTIONAL {{ ?player bb:birthCountry ?birthCountry . }}
        OPTIONAL {{ ?player bb:height ?height . }}
        OPTIONAL {{ ?player bb:weight ?weight . }}

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

    return {
        "name": value_for("name"),
        "player_id": value_for("playerID"),
        "birth_year": value_for("birthYear"),
        "birth_country": value_for("birthCountry"),
        "height": value_for("height"),
        "weight": value_for("weight"),
        "awards_count": value_for("awardsCount", "0"),
        "max_salary": value_for("maxSalary", "0"),
        "career_home_runs": value_for("careerHomeRuns", "0"),
        "career_rbi": value_for("careerRBI", "0"),
        "batting_seasons": value_for("battingSeasons", "0"),
        "search_term": player_id,
    }

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

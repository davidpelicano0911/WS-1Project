from SPARQLWrapper import SPARQLWrapper, JSON

# URL do teu repositório no GraphDB
ENDPOINT = "http://localhost:7200/repositories/baseball"

def get_top_salaries():
    sparql = SPARQLWrapper(ENDPOINT)
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
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]

def get_awards_list():
    sparql = SPARQLWrapper(ENDPOINT)
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
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]
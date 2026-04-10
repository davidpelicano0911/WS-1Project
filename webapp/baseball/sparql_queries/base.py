from rdflib import Graph
from SPARQLWrapper import JSON, XML, SPARQLWrapper

ENDPOINT = "http://localhost:7200/repositories/baseball"

BB_NS   = "http://baseball.ws.pt/"
FOAF_NS = "http://xmlns.com/foaf/0.1/"
RDF_NS  = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD_NS  = "http://www.w3.org/2001/XMLSchema#"


def _shorten_uri(uri: str) -> str:
    """Return a human-readable predicate label from a full URI."""
    for ns in (BB_NS, FOAF_NS, RDF_NS, XSD_NS):
        if uri.startswith(ns):
            return uri[len(ns):]
    if "#" in uri:
        return uri.split("#")[-1]
    return uri.split("/")[-1]


def run_describe(resource_uri: str) -> list[dict]:
    """Execute DESCRIBE and return a sorted list of {predicate, value} dicts."""
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(f"DESCRIBE <{resource_uri}>")
    sparql.setReturnFormat(XML)
    payload = sparql.query().response.read()
    graph = Graph()
    graph.parse(data=payload, format="xml")

    rows = []
    for _s, p, o in graph:
        pred_label = _shorten_uri(str(p))
        # skip rdf:type noise and internal graph URIs
        if pred_label in ("type",):
            continue
        value = str(o)
        # strip XSD datatype suffix  e.g. "1934-02-06"^^xsd:date → "1934-02-06"
        if "^^" in value:
            value = value.split("^^")[0].strip('"')
        rows.append({"predicate": pred_label, "value": value})

    return sorted(rows, key=lambda r: (r["predicate"], r["value"]))


def run_query(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results["results"]["bindings"]


def run_ask(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return bool(results.get("boolean"))


def run_construct(query):
    sparql = SPARQLWrapper(ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(XML)
    response = sparql.query()
    payload = response.response.read()
    graph = Graph()
    graph.parse(data=payload, format="xml")
    return graph


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


def escape_sparql_string(value):
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


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


def _coerce_year_value(year):
    try:
        return int(str(year).strip())
    except (TypeError, ValueError, AttributeError):
        return None

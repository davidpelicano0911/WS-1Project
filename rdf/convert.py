#!/usr/bin/env python3
import argparse
import csv
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, URIRef, XSD
except ModuleNotFoundError as exc:
    if exc.name == "rdflib":
        raise SystemExit(
            "Missing dependency: rdflib\n"
            "Install project dependencies first:\n"
            "  python3 -m venv venv\n"
            "  source venv/bin/activate\n"
            "  pip install -r requirements.txt"
        ) from exc
    raise

# --- Path Configuration ---
BASE = "http://baseball.ws.pt/"
BB = Namespace(BASE)
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

ARCHIVE = Path(__file__).resolve().parent.parent / "archive"
OUT = Path(__file__).resolve().parent / "baseball.n3"
NORMALIZATION_STATS = defaultdict(int)


# --- Conversion Helpers ---
def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]", "_", str(value).strip())


def uri(path: str) -> URIRef:
    return URIRef(BASE + path)


def entity_uri(prefix: str, *parts) -> URIRef:
    return uri("/".join([prefix, *[safe(part) for part in parts]]))


def prop(name: str) -> URIRef:
    return uri(name)


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


COUNTRY_ALIASES = {
    "USA": "United States",
    "U.S.A.": "United States",
    "US": "United States",
    "CAN": "Canada",
    "D.R.": "Dominican Republic",
    "DR": "Dominican Republic",
    "P.R.": "Puerto Rico",
    "PR": "Puerto Rico",
}


def normalize_country(value):
    text = clean_text(value)
    if not text:
        return ""
    return COUNTRY_ALIASES.get(text, text)


def normalize_flag(value):
    text = clean_text(value).upper()
    if not text:
        return ""
    if text in {"Y", "YES", "TRUE", "1", "T"}:
        return "Y"
    if text in {"N", "NO", "FALSE", "0", "F"}:
        return "N"
    return text


def normalize_choice(value, allowed):
    text = clean_text(value).upper()
    return text if text in allowed else ""


def normalize_code(value):
    return clean_text(value).upper()


ROW_NORMALIZERS = {
    "Master.csv": {
        "birthCountry": normalize_country,
        "deathCountry": normalize_country,
        "birthState": clean_text,
        "deathState": clean_text,
        "birthCity": clean_text,
        "deathCity": clean_text,
        "nameFirst": clean_text,
        "nameLast": clean_text,
        "nameGiven": clean_text,
        "bats": lambda value: normalize_choice(value, {"R", "L", "B"}),
        "throws": lambda value: normalize_choice(value, {"R", "L"}),
        "retroID": normalize_code,
        "bbrefID": clean_text,
    },
    "TeamsFranchises.csv": {
        "franchID": normalize_code,
        "franchName": clean_text,
        "active": normalize_flag,
        "NAassoc": clean_text,
    },
    "Teams.csv": {
        "lgID": normalize_code,
        "teamID": normalize_code,
        "franchID": normalize_code,
        "divID": normalize_code,
        "DivWin": normalize_flag,
        "WCWin": normalize_flag,
        "LgWin": normalize_flag,
        "WSWin": normalize_flag,
        "name": clean_text,
        "park": clean_text,
        "teamIDBR": normalize_code,
        "teamIDlahman45": normalize_code,
        "teamIDretro": normalize_code,
    },
    "TeamsHalf.csv": {
        "lgID": normalize_code,
        "teamID": normalize_code,
        "divID": normalize_code,
        "DivWin": normalize_flag,
    },
    "Batting.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
    },
    "BattingPost.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
        "round": normalize_code,
    },
    "Pitching.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
    },
    "PitchingPost.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
        "round": normalize_code,
    },
    "Fielding.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
        "POS": normalize_code,
    },
    "FieldingOF.csv": {
        "playerID": clean_text,
    },
    "Salaries.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
    },
    "AwardsPlayers.csv": {
        "playerID": clean_text,
        "awardID": clean_text,
        "lgID": normalize_code,
        "tie": normalize_flag,
        "notes": clean_text,
    },
    "AwardsSharePlayers.csv": {
        "awardID": clean_text,
        "lgID": normalize_code,
        "playerID": clean_text,
    },
    "HallOfFame.csv": {
        "playerID": clean_text,
        "votedBy": clean_text,
        "inducted": normalize_flag,
        "category": clean_text,
        "needed_note": clean_text,
    },
    "AllstarFull.csv": {
        "playerID": clean_text,
        "gameID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
    },
    "Managers.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
        "plyrMgr": normalize_flag,
    },
    "ManagersHalf.csv": {
        "playerID": clean_text,
        "teamID": normalize_code,
        "lgID": normalize_code,
    },
    "AwardsManagers.csv": {
        "playerID": clean_text,
        "awardID": clean_text,
        "lgID": normalize_code,
        "tie": normalize_flag,
        "notes": clean_text,
    },
    "AwardsShareManagers.csv": {
        "awardID": clean_text,
        "lgID": normalize_code,
        "playerID": clean_text,
    },
    "SeriesPost.csv": {
        "round": normalize_code,
        "teamIDwinner": normalize_code,
        "lgIDwinner": normalize_code,
        "teamIDloser": normalize_code,
        "lgIDloser": normalize_code,
    },
}


def normalize_row(filename, row):
    normalizers = ROW_NORMALIZERS.get(filename)
    if not normalizers:
        return row

    normalized = dict(row)
    for column, normalizer in normalizers.items():
        original = row.get(column)
        updated = normalizer(original)
        normalized[column] = updated
        if (original or "") != updated:
            NORMALIZATION_STATS[f"{filename}:{column}"] += 1
    return normalized


def lit(value, datatype=None):
    if value is None:
        return None
    v = str(value).strip()
    if v.lower() in ("", "na", "n/a", "nan", "none", "null", "-"):
        return None
    return Literal(v, datatype=datatype)


def lit_int(value):
    base = lit(value)
    if base is None:
        return None
    try:
        return Literal(int(str(base)), datatype=XSD.integer)
    except ValueError:
        return None


def lit_float(value):
    base = lit(value)
    if base is None:
        return None
    try:
        return Literal(Decimal(str(base)), datatype=XSD.decimal)
    except InvalidOperation:
        return None


def lit_bool(value):
    if value is None:
        return None
    val = str(value).strip().upper()
    if val in ("Y", "TRUE", "1"):
        return Literal(True, datatype=XSD.boolean)
    if val in ("N", "FALSE", "0"):
        return Literal(False, datatype=XSD.boolean)
    return None


def lit_date(value):
    return lit(value, XSD.date)


def add_fields(subject, row, specs):
    for spec in specs:
        if isinstance(spec, str):
            column, converter, predicate_name = spec, lit, spec
        elif len(spec) == 2:
            column, converter = spec
            predicate_name = column
        else:
            column, converter, predicate_name = spec
        add(subject, prop(predicate_name), converter(row.get(column)))


# --- Streaming Writer Engine ---
namespace_graph = Graph()
namespace_graph.bind("bb", BB)
namespace_graph.bind("foaf", FOAF)
namespace_graph.bind("rdf", RDF)
namespace_graph.bind("rdfs", RDFS)
namespace_graph.bind("owl", OWL)
namespace_graph.bind("xsd", XSD)
namespace_manager = namespace_graph.namespace_manager

out_file = open(OUT, "w", encoding="utf-8")
out_file.write("@prefix bb: <http://baseball.ws.pt/> .\n")
out_file.write("@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n")
out_file.write("@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n")
out_file.write("@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")
out_file.write("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n")
out_file.write("@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n")


def term_n3(term):
    return term.n3(namespace_manager)


def add(s, p, o):
    if s and p and o is not None:
        out_file.write(f"{term_n3(s)} {term_n3(p)} {term_n3(o)} .\n")


def read_csv(filename: str):
    path = ARCHIVE / filename
    if not path.exists():
        print(f"  [SKIP] {filename} not found", file=sys.stderr)
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            yield normalize_row(filename, row)


def print_normalization_summary():
    if not NORMALIZATION_STATS:
        print("No preprocessing changes were needed.")
        return

    print("\nPreprocessing summary:")
    for key in sorted(NORMALIZATION_STATS):
        print(f"  {key}: {NORMALIZATION_STATS[key]} normalized values")


# --- Field Specifications ---
MASTER_FIELDS = [
    "playerID",
    ("birthYear", lit_int),
    ("birthMonth", lit_int),
    ("birthDay", lit_int),
    "birthCountry",
    "birthState",
    "birthCity",
    ("deathYear", lit_int),
    ("deathMonth", lit_int),
    ("deathDay", lit_int),
    "deathCountry",
    "deathState",
    "deathCity",
    "nameFirst",
    "nameLast",
    "nameGiven",
    ("weight", lit_int),
    ("height", lit_int),
    "bats",
    "throws",
    ("debut", lit_date),
    ("finalGame", lit_date),
    "retroID",
    "bbrefID",
]

FRANCHISE_FIELDS = [
    "franchID",
    "franchName",
    ("active", lit_bool),
    "NAassoc",
]

TEAM_FIELDS = [
    ("yearID", lit_int),
    "lgID",
    "teamID",
    "franchID",
    "divID",
    ("Rank", lit_int),
    ("G", lit_int),
    ("Ghome", lit_int),
    ("W", lit_int),
    ("L", lit_int),
    ("DivWin", lit_bool),
    ("WCWin", lit_bool),
    ("LgWin", lit_bool),
    ("WSWin", lit_bool),
    ("R", lit_int),
    ("AB", lit_int),
    ("H", lit_int),
    ("2B", lit_int),
    ("3B", lit_int),
    ("HR", lit_int),
    ("BB", lit_int),
    ("SO", lit_int),
    ("SB", lit_int),
    ("CS", lit_int),
    ("HBP", lit_int),
    ("SF", lit_int),
    ("RA", lit_int),
    ("ER", lit_int),
    ("ERA", lit_float),
    ("CG", lit_int),
    ("SHO", lit_int),
    ("SV", lit_int),
    ("IPouts", lit_int),
    ("HA", lit_int),
    ("HRA", lit_int),
    ("BBA", lit_int),
    ("SOA", lit_int),
    ("E", lit_int),
    ("DP", lit_int),
    ("FP", lit_float),
    "name",
    "park",
    ("attendance", lit_int),
    ("BPF", lit_int),
    ("PPF", lit_int),
    "teamIDBR",
    "teamIDlahman45",
    "teamIDretro",
]

BATTING_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    ("stint", lit_int),
    "teamID",
    "lgID",
    ("G", lit_int),
    ("AB", lit_int),
    ("R", lit_int),
    ("H", lit_int),
    ("2B", lit_int),
    ("3B", lit_int),
    ("HR", lit_int),
    ("RBI", lit_int),
    ("SB", lit_int),
    ("CS", lit_int),
    ("BB", lit_int),
    ("SO", lit_int),
    ("IBB", lit_int),
    ("HBP", lit_int),
    ("SH", lit_int),
    ("SF", lit_int),
    ("GIDP", lit_int),
]

PITCHING_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    ("stint", lit_int),
    "teamID",
    "lgID",
    ("W", lit_int),
    ("L", lit_int),
    ("G", lit_int),
    ("GS", lit_int),
    ("CG", lit_int),
    ("SHO", lit_int),
    ("SV", lit_int),
    ("IPouts", lit_int),
    ("H", lit_int),
    ("ER", lit_int),
    ("HR", lit_int),
    ("BB", lit_int),
    ("SO", lit_int),
    ("BAOpp", lit_float),
    ("ERA", lit_float),
    ("IBB", lit_int),
    ("WP", lit_int),
    ("HBP", lit_int),
    ("BK", lit_int),
    ("BFP", lit_int),
    ("GF", lit_int),
    ("R", lit_int),
    ("SH", lit_int),
    ("SF", lit_int),
    ("GIDP", lit_int),
]

FIELDING_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    ("stint", lit_int),
    "teamID",
    "lgID",
    "POS",
    ("G", lit_int),
    ("GS", lit_int),
    ("InnOuts", lit_int),
    ("PO", lit_int),
    ("A", lit_int),
    ("E", lit_int),
    ("DP", lit_int),
    ("PB", lit_int),
    ("WP", lit_int),
    ("SB", lit_int),
    ("CS", lit_int),
    ("ZR", lit_float),
]

FIELDING_OF_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    ("stint", lit_int),
    ("Glf", lit_int),
    ("Gcf", lit_int),
    ("Grf", lit_int),
]

HALL_OF_FAME_FIELDS = [
    "playerID",
    ("yearid", lit_int),
    "votedBy",
    ("ballots", lit_int),
    ("needed", lit_int),
    ("votes", lit_int),
    ("inducted", lit_bool),
    "category",
    "needed_note",
]

ALLSTAR_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    ("gameNum", lit_int),
    "gameID",
    "teamID",
    "lgID",
    ("GP", lit_int),
    ("startingPos", lit_int),
]

MANAGER_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    "teamID",
    "lgID",
    ("inseason", lit_int),
    ("G", lit_int),
    ("W", lit_int),
    ("L", lit_int),
    ("rank", lit_int),
    ("plyrMgr", lit_bool),
]

AWARD_FIELDS = [
    "playerID",
    "awardID",
    ("yearID", lit_int),
    "lgID",
    ("tie", lit_bool),
    "notes",
]

AWARD_SHARE_FIELDS = [
    "awardID",
    ("yearID", lit_int),
    "lgID",
    "playerID",
    ("pointsWon", lit_float),
    ("pointsMax", lit_float),
    ("votesFirst", lit_float),
]

TEAM_HALF_FIELDS = [
    ("yearID", lit_int),
    "lgID",
    "teamID",
    ("Half", lit_int),
    "divID",
    ("DivWin", lit_bool),
    ("Rank", lit_int),
    ("G", lit_int),
    ("W", lit_int),
    ("L", lit_int),
]

MANAGER_HALF_FIELDS = [
    "playerID",
    ("yearID", lit_int),
    "teamID",
    "lgID",
    ("inseason", lit_int),
    ("half", lit_int),
    ("G", lit_int),
    ("W", lit_int),
    ("L", lit_int),
    ("rank", lit_int),
]

SERIES_POST_FIELDS = [
    ("yearID", lit_int),
    "round",
    "teamIDwinner",
    "lgIDwinner",
    "teamIDloser",
    "lgIDloser",
    ("wins", lit_int),
    ("losses", lit_int),
    ("ties", lit_int),
]


# --- Conversion Functions ---
def declare_ontology():
    classes = [
        "Player",
        "Franchise",
        "Team",
        "TeamHalf",
        "BattingStat",
        "BattingPostStat",
        "PitchingStat",
        "PitchingPostStat",
        "FieldingStat",
        "FieldingOFStat",
        "Salary",
        "HallOfFameVote",
        "Award",
        "AwardShare",
        "ManagerAwardShare",
        "WorldSeriesResult",
        "AllStarAppearance",
        "Manager",
        "ManagerHalf",
    ]
    for cls in classes:
        add(BB[cls], RDF.type, OWL.Class)
        add(BB[cls], RDFS.label, Literal(cls))


def convert_master():
    print("  Processing Players...")
    for row in read_csv("Master.csv"):
        pid = row.get("playerID")
        if not pid:
            continue

        s = entity_uri("player", pid)
        add(s, RDF.type, BB.Player)
        add_fields(s, row, MASTER_FIELDS)

        add(s, BB.playerID, lit(pid))
        add(s, BB.firstName, lit(row.get("nameFirst")))
        add(s, BB.lastName, lit(row.get("nameLast")))
        add(s, BB.birthCountry, lit(row.get("birthCountry")))
        add(s, BB.birthYear, lit_int(row.get("birthYear")))
        add(s, BB.weight, lit_int(row.get("weight")))
        add(s, BB.height, lit_int(row.get("height")))
        add(s, BB.debut, lit_date(row.get("debut")))
        add(s, FOAF.name, lit(row.get("nameGiven") or f"{row.get('nameFirst', '')} {row.get('nameLast', '')}".strip()))


def convert_franchises():
    print("  Processing Franchises...")
    for row in read_csv("TeamsFranchises.csv"):
        fid = row.get("franchID")
        if not fid:
            continue

        s = entity_uri("franchise", fid)
        add(s, RDF.type, BB.Franchise)
        add_fields(s, row, FRANCHISE_FIELDS)
        add(s, BB.franchiseName, lit(row.get("franchName")))


def convert_teams():
    print("  Processing Teams...")
    for row in read_csv("Teams.csv"):
        tid = row.get("teamID")
        year = row.get("yearID")
        fid = row.get("franchID")
        if not tid or not year:
            continue

        s = entity_uri("team", tid, year)
        add(s, RDF.type, BB.Team)
        add_fields(s, row, TEAM_FIELDS)
        add(s, BB.teamName, lit(row.get("name")))
        add(s, BB.yearID, lit_int(year))
        if fid:
            add(s, BB.franchiseOf, entity_uri("franchise", fid))


def convert_teams_half():
    print("  Processing TeamsHalf...")
    for row in read_csv("TeamsHalf.csv"):
        tid = row.get("teamID")
        year = row.get("yearID")
        half = row.get("Half")
        if not tid or not year or not half:
            continue

        s = entity_uri("teamhalf", tid, year, half)
        add(s, RDF.type, BB.TeamHalf)
        add_fields(s, row, TEAM_HALF_FIELDS)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_batting():
    print("  Processing Batting (Large File)...")
    for row in read_csv("Batting.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        stint = row.get("stint", "1")
        tid = row.get("teamID")
        if not pid or not year or not tid:
            continue

        s = entity_uri("batting", pid, year, stint)
        add(s, RDF.type, BB.BattingStat)
        add_fields(s, row, BATTING_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.homeRuns, lit_int(row.get("HR")))
        add(s, BB.RBI, lit_int(row.get("RBI")))
        add(entity_uri("player", pid), BB.hasBatting, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_batting_post():
    print("  Processing BattingPost...")
    for row in read_csv("BattingPost.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        round_id = row.get("round")
        tid = row.get("teamID")
        if not pid or not year or not round_id or not tid:
            continue

        s = entity_uri("battingpost", pid, year, round_id, tid)
        add(s, RDF.type, BB.BattingPostStat)
        add_fields(s, row, [("round", lit)] + BATTING_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.homeRuns, lit_int(row.get("HR")))
        add(s, BB.RBI, lit_int(row.get("RBI")))
        add(entity_uri("player", pid), BB.hasBatting, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_pitching():
    print("  Processing Pitching...")
    for row in read_csv("Pitching.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        stint = row.get("stint", "1")
        tid = row.get("teamID")
        if not pid or not year or not tid:
            continue

        s = entity_uri("pitching", pid, year, stint)
        add(s, RDF.type, BB.PitchingStat)
        add_fields(s, row, PITCHING_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.ERA, lit_float(row.get("ERA")))
        add(entity_uri("player", pid), BB.hasPitching, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_pitching_post():
    print("  Processing PitchingPost...")
    for row in read_csv("PitchingPost.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        round_id = row.get("round")
        tid = row.get("teamID")
        if not pid or not year or not round_id or not tid:
            continue

        s = entity_uri("pitchingpost", pid, year, round_id, tid)
        add(s, RDF.type, BB.PitchingPostStat)
        add_fields(s, row, [("round", lit)] + PITCHING_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.ERA, lit_float(row.get("ERA")))
        add(entity_uri("player", pid), BB.hasPitching, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_salaries():
    print("  Processing Salaries...")
    for row in read_csv("Salaries.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        tid = row.get("teamID")
        if not pid or not year or not tid:
            continue

        s = entity_uri("salary", pid, year, tid)
        add(s, RDF.type, BB.Salary)
        add_fields(s, row, [("yearID", lit_int), "teamID", "lgID", "playerID", ("salary", lit_int)])
        add(s, BB.salary, lit_int(row.get("salary")))
        add(s, BB.yearID, lit_int(year))
        add(entity_uri("player", pid), BB.hasSalary, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_awards():
    print("  Processing Awards...")
    for row in read_csv("AwardsPlayers.csv"):
        pid = row.get("playerID")
        award = row.get("awardID")
        year = row.get("yearID")
        lg = row.get("lgID")
        if not pid or not award or not year or not lg:
            continue

        s = entity_uri("award", pid, award, year, lg)
        add(s, RDF.type, BB.Award)
        add_fields(s, row, AWARD_FIELDS)
        add(s, BB.awardName, lit(award))
        add(s, BB.yearID, lit_int(year))
        add(s, BB.lgID, lit(lg))
        add(s, BB.notes, lit(row.get("notes")))
        add(s, BB.tie, lit_bool(row.get("tie")))
        add(entity_uri("player", pid), BB.wonAward, s)


def convert_awards_share_players():
    print("  Processing AwardsSharePlayers...")
    for row in read_csv("AwardsSharePlayers.csv"):
        pid = row.get("playerID")
        award = row.get("awardID")
        year = row.get("yearID")
        lg = row.get("lgID")
        if not pid or not award or not year or not lg:
            continue

        s = entity_uri("awardshareplayer", pid, award, year, lg)
        add(s, RDF.type, BB.AwardShare)
        add_fields(s, row, AWARD_SHARE_FIELDS)


def convert_fielding():
    print("  Processing Fielding (Large File)...")
    for row in read_csv("Fielding.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        stint = row.get("stint", "1")
        tid = row.get("teamID")
        if not pid or not year or not tid:
            continue

        s = entity_uri("fielding", pid, year, stint)
        add(s, RDF.type, BB.FieldingStat)
        add_fields(s, row, FIELDING_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.POS, lit(row.get("POS")))
        add(s, BB.G, lit_int(row.get("G")))
        add(s, BB.E, lit_int(row.get("E")))
        add(entity_uri("player", pid), BB.hasFielding, s)
        add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_fielding_of():
    print("  Processing FieldingOF...")
    for row in read_csv("FieldingOF.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        stint = row.get("stint", "1")
        if not pid or not year:
            continue

        s = entity_uri("fieldingof", pid, year, stint)
        add(s, RDF.type, BB.FieldingOFStat)
        add_fields(s, row, FIELDING_OF_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(entity_uri("player", pid), BB.hasFieldingOF, s)


def convert_hall_of_fame():
    print("  Processing HallOfFame...")
    for row in read_csv("HallOfFame.csv"):
        pid = row.get("playerID")
        yearid = row.get("yearid")
        if not pid or not yearid:
            continue

        s = entity_uri("halloffame", pid, yearid)
        add(s, RDF.type, BB.HallOfFameVote)
        add_fields(s, row, HALL_OF_FAME_FIELDS)
        add(s, BB.yearID, lit_int(yearid))
        add(s, BB.votedBy, lit(row.get("votedBy")))
        add(s, BB.ballots, lit_int(row.get("ballots")))
        add(s, BB.needed, lit_int(row.get("needed")))
        add(s, BB.votes, lit_int(row.get("votes")))
        add(s, BB.inducted, lit_bool(row.get("inducted")))
        add(s, BB.category, lit(row.get("category")))
        add(entity_uri("player", pid), BB.hallOfFameVote, s)


def convert_allstar_full():
    print("  Processing AllStarFull...")
    for row in read_csv("AllstarFull.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        game_num = row.get("gameNum")
        tid = row.get("teamID")
        if not pid or not year or game_num is None:
            continue

        s = entity_uri("allstar", pid, year, game_num)
        add(s, RDF.type, BB.AllStarAppearance)
        add_fields(s, row, ALLSTAR_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.gameID, lit(row.get("gameID")))
        add(s, BB.startingPos, lit_int(row.get("startingPos")))
        add(entity_uri("player", pid), BB.playedInAllStar, s)
        if tid:
            add(s, BB.teamOf, entity_uri("team", tid, year))


def convert_managers():
    print("  Processing Managers...")
    for row in read_csv("Managers.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        inseason = row.get("inseason", "1")
        tid = row.get("teamID")
        if not pid or not year or not tid:
            continue

        s = entity_uri("manager", pid, year, inseason)
        add(s, RDF.type, BB.Manager)
        add_fields(s, row, MANAGER_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.wins, lit_int(row.get("W")))
        add(s, BB.losses, lit_int(row.get("L")))
        add(s, BB.rank, lit_int(row.get("rank")))
        add(entity_uri("player", pid), BB.isManager, s)
        add(s, BB.managedTeam, entity_uri("team", tid, year))


def convert_managers_half():
    print("  Processing ManagersHalf...")
    for row in read_csv("ManagersHalf.csv"):
        pid = row.get("playerID")
        year = row.get("yearID")
        inseason = row.get("inseason", "1")
        half = row.get("half")
        tid = row.get("teamID")
        if not pid or not year or not tid or not half:
            continue

        s = entity_uri("managerhalf", pid, year, inseason, half)
        add(s, RDF.type, BB.ManagerHalf)
        add_fields(s, row, MANAGER_HALF_FIELDS)
        add(s, BB.managedTeam, entity_uri("team", tid, year))
        add(entity_uri("player", pid), BB.isManager, s)


def convert_awards_managers():
    print("  Processing AwardsManagers...")
    for row in read_csv("AwardsManagers.csv"):
        pid = row.get("playerID")
        award = row.get("awardID")
        year = row.get("yearID")
        lg = row.get("lgID")
        if not pid or not award or not year:
            continue

        s = entity_uri("awardmgr", pid, award, year, lg or "unknown")
        add(s, RDF.type, BB.Award)
        add_fields(s, row, AWARD_FIELDS)
        add(s, BB.awardName, lit(award))
        add(s, BB.yearID, lit_int(year))
        add(entity_uri("player", pid), BB.wonAward, s)


def convert_awards_share_managers():
    print("  Processing AwardsShareManagers...")
    for row in read_csv("AwardsShareManagers.csv"):
        pid = row.get("playerID")
        award = row.get("awardID")
        year = row.get("yearID")
        lg = row.get("lgID")
        if not pid or not award or not year or not lg:
            continue

        s = entity_uri("awardsharemanager", pid, award, year, lg)
        add(s, RDF.type, BB.ManagerAwardShare)
        add_fields(s, row, AWARD_SHARE_FIELDS)


def convert_series_post():
    print("  Processing SeriesPost...")
    for row in read_csv("SeriesPost.csv"):
        year = row.get("yearID")
        round_id = row.get("round")
        if not year or not round_id:
            continue

        s = entity_uri("seriespost", year, round_id)
        add(s, RDF.type, BB.WorldSeriesResult)
        add_fields(s, row, SERIES_POST_FIELDS)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.round, lit(round_id))
        
        add(s, BB.wins, lit_int(row.get("wins")))
        add(s, BB.losses, lit_int(row.get("losses")))
        add(s, BB.ties, lit_int(row.get("ties")))

        add(s, BB.lgIDwinner, lit(row.get("lgIDwinner"))) 
        add(s, BB.lgIDloser, lit(row.get("lgIDloser")))    

        w_team = row.get("teamIDwinner")
        l_team = row.get("teamIDloser")
        if w_team:
            add(s, BB.winnerTeam, entity_uri("team", w_team, year))
        if l_team:
            add(s, BB.loserTeam, entity_uri("team", l_team, year))


CONVERSION_PROFILES = {
    "lean": [
        ("Players", convert_master),
        ("Franchises", convert_franchises),
        ("Teams", convert_teams),
        ("Batting", convert_batting),
        ("Pitching", convert_pitching),
        ("Salaries", convert_salaries),
        ("Awards", convert_awards),
        ("Hall of Fame", convert_hall_of_fame),
        ("All-Star", convert_allstar_full),
        ("Managers", convert_managers),
        ("Series/Postseason", convert_series_post),
    ],
    "full": [
        ("Players", convert_master),
        ("Franchises", convert_franchises),
        ("Teams", convert_teams),
        ("TeamsHalf", convert_teams_half),
        ("Batting", convert_batting),
        ("BattingPost", convert_batting_post),
        ("Pitching", convert_pitching),
        ("PitchingPost", convert_pitching_post),
        ("Salaries", convert_salaries),
        ("Awards", convert_awards),
        ("AwardsSharePlayers", convert_awards_share_players),
        ("Fielding", convert_fielding),
        ("FieldingOF", convert_fielding_of),
        ("Hall of Fame", convert_hall_of_fame),
        ("All-Star", convert_allstar_full),
        ("Managers", convert_managers),
        ("ManagersHalf", convert_managers_half),
        ("AwardsManagers", convert_awards_managers),
        ("AwardsShareManagers", convert_awards_share_managers),
        ("Series/Postseason", convert_series_post),
    ],
}


def parse_args():
    parser = argparse.ArgumentParser(description="Convert Lahman baseball CSV data to RDF/N3.")
    parser.add_argument(
        "--profile",
        choices=sorted(CONVERSION_PROFILES),
        default="lean",
        help="Export profile. 'lean' keeps only data currently used by the web app; 'full' exports everything.",
    )
    return parser.parse_args()
# --- Main ---
def main():
    args = parse_args()
    try:
        print(f"Starting RDF conversion (Streaming Mode, profile={args.profile})...")
        declare_ontology()
        for _label, converter in CONVERSION_PROFILES[args.profile]:
            converter()

        print_normalization_summary()
        print(f"\nSuccess! File generated: {OUT}")
        print(f"Size: {OUT.stat().st_size / 1024 / 1024:.2f} MB")
    finally:
        out_file.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path
from rdflib import Literal, Namespace, RDF, RDFS, OWL, URIRef, XSD

# --- Path Configuration ---
BASE = "http://baseball.ws.pt/"
BB   = Namespace(BASE)
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

# Automatic paths based on script location
ARCHIVE = Path(__file__).resolve().parent.parent / "archive"
OUT     = Path(__file__).resolve().parent / "baseball.nt"

# --- Conversion Helpers ---
def safe(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]", "_", str(value).strip())

def uri(path: str) -> URIRef:
    return URIRef(BASE + path)

def lit(value, datatype=None):
    v = str(value).strip()
    if v in ("", "NA", "N/A", "nan"):
        return None
    return Literal(v, datatype=datatype)

def lit_int(v): return lit(v, XSD.integer)
def lit_float(v): return lit(v, XSD.decimal)

def lit_bool(v): 
    val = str(v).strip().upper()
    if val in ("Y", "TRUE", "1"): return Literal(True, datatype=XSD.boolean)
    if val in ("N", "FALSE", "0"): return Literal(False, datatype=XSD.boolean)
    return None

def lit_date(v): return lit(v, XSD.date)

# --- Streaming Writer Engine ---
# Open output file at the start
out_file = open(OUT, "w", encoding="utf-8")

def add(s, p, o):
    """Writes a triple directly to the file in N-Triples format."""
    if s and p and o is not None:
        # N-Triples format: <subject> <predicate> <object> .
        line = f"<{s}> <{p}> {o.n3()} .\n"
        out_file.write(line)

def read_csv(filename: str):
    path = ARCHIVE / filename
    if not path.exists():
        print(f"  [SKIP] {filename} not found", file=sys.stderr)
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        yield from csv.DictReader(f)

# --- Conversion Functions ---

def declare_ontology():
    classes = ["Player", "Franchise", "Team", "BattingStat", "PitchingStat", "FieldingStat", "Salary", "HallOfFameVote", "Award", "WorldSeriesResult", "AllStarAppearance", "Manager"]
    for cls in classes:
        add(BB[cls], RDF.type, OWL.Class)
        add(BB[cls], RDFS.label, Literal(cls))

def convert_master():
    print("  Processing Players...")
    for row in read_csv("Master.csv"):
        pid = row.get("playerID")
        if not pid: continue
        s = uri(f"player/{safe(pid)}")
        add(s, RDF.type, BB.Player)
        add(s, BB.playerID, lit(pid))
        add(s, BB.firstName, lit(row.get("nameFirst")))
        add(s, BB.lastName, lit(row.get("nameLast")))
        add(s, FOAF.name, lit(f"{row.get('nameFirst','')} {row.get('nameLast','')}".strip()))
        add(s, BB.birthCountry, lit(row.get("birthCountry")))
        add(s, BB.birthYear, lit_int(row.get("birthYear")))
        add(s, BB.weight, lit_int(row.get("weight")))
        add(s, BB.height, lit_int(row.get("height")))
        add(s, BB.debut, lit_date(row.get("debut")))

def convert_franchises():
    print("  Processing Franchises...")
    for row in read_csv("TeamsFranchises.csv"):
        fid = row.get("franchID")
        if not fid: continue
        s = uri(f"franchise/{safe(fid)}")
        add(s, RDF.type, BB.Franchise)
        add(s, BB.franchiseName, lit(row.get("franchName")))

def convert_teams():
    print("  Processing Teams...")
    for row in read_csv("Teams.csv"):
        tid, year, fid = row.get("teamID"), row.get("yearID"), row.get("franchID")
        if not tid or not year: continue
        s = uri(f"team/{safe(tid)}/{safe(year)}")
        add(s, RDF.type, BB.Team)
        add(s, BB.teamName, lit(row.get("name")))
        add(s, BB.yearID, lit_int(year))
        if fid: add(s, BB.franchiseOf, uri(f"franchise/{safe(fid)}"))

def convert_batting():
    print("  Processing Batting (Large File)...")
    for row in read_csv("Batting.csv"):
        pid, year, stint, tid = row.get("playerID"), row.get("yearID"), row.get("stint", "1"), row.get("teamID")
        if not pid or not year or not tid: continue
        
        s = uri(f"batting/{safe(pid)}/{safe(year)}/{safe(stint)}")
        add(s, RDF.type, BB.BattingStat)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.homeRuns, lit_int(row.get("HR")))
        add(s, BB.RBI, lit_int(row.get("RBI")))
        
        add(uri(f"player/{safe(pid)}"), BB.hasBatting, s)
        add(s, BB.teamOf, uri(f"team/{safe(tid)}/{safe(year)}"))

def convert_pitching():
    print("  Processing Pitching...")
    for row in read_csv("Pitching.csv"):
        pid, year, stint, tid = row.get("playerID"), row.get("yearID"), row.get("stint", "1"), row.get("teamID")
        if not pid or not year or not tid: continue
        
        s = uri(f"pitching/{safe(pid)}/{safe(year)}/{safe(stint)}")
        add(s, RDF.type, BB.PitchingStat)
        add(s, BB.yearID, lit_int(year))
        add(s, BB.ERA, lit_float(row.get("ERA")))
        
        add(uri(f"player/{safe(pid)}"), BB.hasPitching, s)
        add(s, BB.teamOf, uri(f"team/{safe(tid)}/{safe(year)}"))

def convert_salaries():
    print("  Processing Salaries...")
    for row in read_csv("Salaries.csv"):
        pid, year, tid = row.get("playerID"), row.get("yearID"), row.get("teamID")
        if not pid or not year or not tid: continue
        
        s = uri(f"salary/{safe(pid)}/{safe(year)}/{safe(tid)}")
        add(s, BB.salary, lit_int(row.get("salary")))
        add(s, BB.yearID, lit_int(year))
        
        add(uri(f"player/{safe(pid)}"), BB.hasSalary, s)
        add(s, BB.teamOf, uri(f"team/{safe(tid)}/{safe(year)}"))

def convert_awards():
    print("  Processing Awards...")
    for row in read_csv("AwardsPlayers.csv"):
        pid, award, year = row.get("playerID"), row.get("awardID"), row.get("yearID")
        if not pid: continue
        s = uri(f"award/{safe(pid)}/{safe(award)}/{safe(year)}")
        add(s, BB.awardName, lit(award))
        add(uri(f"player/{safe(pid)}"), BB.wonAward, s)
        add(s, BB.yearID, lit_int(year))

# --- Main ---
def main():
    try:
        print("Starting RDF conversion (Streaming Mode)...")
        declare_ontology()
        convert_master()
        convert_franchises()
        convert_teams()
        convert_batting()
        convert_pitching()
        convert_salaries()
        convert_awards()
        
        print(f"\nSuccess! File generated: {OUT}")
        print(f"Size: {OUT.stat().st_size / 1024 / 1024:.2f} MB")
    finally:
        out_file.close()

if __name__ == "__main__":
    main()
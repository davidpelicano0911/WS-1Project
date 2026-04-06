from functools import lru_cache

from .sparql import get_header_teams_graph

# MLB Stats API / MLB static logo ids for current franchises.
MLB_LOGO_IDS = {
    "ARI": 109,
    "ATL": 144,
    "BAL": 110,
    "BOS": 111,
    "CHC": 112,
    "CHW": 145,
    "CIN": 113,
    "CLE": 114,
    "COL": 115,
    "DET": 116,
    "HOU": 117,
    "KCR": 118,
    "LAA": 108,
    "LAD": 119,
    "MIA": 146,
    "MIL": 158,
    "MIN": 142,
    "NYM": 121,
    "NYY": 147,
    "OAK": 133,
    "PHI": 143,
    "PIT": 134,
    "SDP": 135,
    "SEA": 136,
    "SFG": 137,
    "STL": 138,
    "TBR": 139,
    "TEX": 140,
    "TOR": 141,
    "WSN": 120,
}

TEAM_CODE_NORMALIZATION = {
    "ANA": "LAA",
    "CAL": "LAA",
    "CHA": "CHW",
    "CHN": "CHC",
    "KCA": "KCR",
    "LAN": "LAD",
    "MON": "WSN",
    "NYA": "NYY",
    "NYN": "NYM",
    "SDN": "SDP",
    "SFN": "SFG",
    "SLN": "STL",
    "TBA": "TBR",
}


@lru_cache(maxsize=1)
def get_header_teams():
    try:
        teams = get_header_teams_graph()
    except Exception:
        return []

    for team in teams:
        normalized_abbr = TEAM_CODE_NORMALIZATION.get(team["abbr"], team["abbr"])
        team["abbr"] = normalized_abbr
        team["mlb_logo_id"] = MLB_LOGO_IDS.get(normalized_abbr)

    return teams

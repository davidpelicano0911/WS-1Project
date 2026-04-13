import re
import unicodedata

from django.urls import reverse

from ..sparql import LEAGUE_LABELS
from .queries import (
    find_players_by_name,
    find_teams_by_name,
    get_awards_by_year,
    get_players_by_country,
    get_salary_leaders,
    get_teams_by_league_code,
)

CHATBOT_SUGGESTIONS = [
    "Show AL teams",
    "Players from Cuba",
    "Awards in 2015",
    "Top salaries",
    "Find player Aaron Judge",
    "Find team Boston Red Sox",
]

LEAGUE_ALIASES = {
    "al": "AL",
    "american league": "AL",
    "liga americana": "AL",
    "nl": "NL",
    "national league": "NL",
    "liga nacional": "NL",
    "aa": "AA",
    "american association": "AA",
    "na": "NA",
    "national association": "NA",
    "ua": "UA",
    "union association": "UA",
    "pl": "PL",
    "players league": "PL",
    "players' league": "PL",
    "fl": "FL",
    "federal league": "FL",
}

TEAM_KEYWORDS_PATTERN = re.compile(
    r"\b(team|teams|club|clubs|equipa|equipas|equipe|equipes|time|times|clube|clubes|franquia|franquias)\b",
    re.IGNORECASE,
)
SALARY_KEYWORDS_PATTERN = re.compile(r"\b(salary|salaries|paid|salario|salarios|salário|salários)\b", re.IGNORECASE)


def _normalize_message(message):
    return " ".join(str(message or "").strip().split())


def _fold_text(message):
    normalized = unicodedata.normalize("NFKD", str(message or ""))
    return "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()


def _help_payload():
    return {
        "answer": "Ask about players, teams, leagues, awards, or salaries. I answer with live GraphDB data.",
        "items": [
            {"label": "Players", "meta": "Open the player catalog", "url": reverse("players"), "kind": "Page"},
            {"label": "Teams", "meta": "Open the team directory", "url": reverse("teams"), "kind": "Page"},
            {"label": "Analytics", "meta": "Explore awards, salaries, and leaders", "url": reverse("analytics"), "kind": "Page"},
        ],
        "suggestions": CHATBOT_SUGGESTIONS,
    }


def _extract_league_code(message):
    lowered = _fold_text(_normalize_message(message))
    for alias in sorted(LEAGUE_ALIASES, key=len, reverse=True):
        alias_folded = _fold_text(alias)
        if re.search(rf"(?<![a-z]){re.escape(alias_folded)}(?![a-z])", lowered):
            return LEAGUE_ALIASES[alias]
    return ""


def _build_player_items(players):
    items = []
    for player in players:
        player_id = player.get("player_id")
        if not player_id:
            continue
        meta = " · ".join(bit for bit in [player.get("birth_country"), player.get("debut")] if bit)
        items.append(
            {
                "label": player.get("name") or player_id,
                "meta": meta or player_id,
                "url": reverse("player_detail", args=[player_id]),
                "kind": "Player",
            }
        )
    return items


def _build_team_items(teams):
    items = []
    for team in teams:
        franchise_id = team.get("franchise_id")
        if not franchise_id:
            continue
        year_span = ""
        if team.get("first_year") and team.get("last_year"):
            year_span = f'{team["first_year"]}-{team["last_year"]}'
        elif team.get("latest_year"):
            year_span = str(team["latest_year"])
        meta = " · ".join(
            bit
            for bit in [
                LEAGUE_LABELS.get(team.get("league_code"), team.get("league_code") or ""),
                year_span,
            ]
            if bit
        )
        items.append(
            {
                "label": team.get("name") or franchise_id,
                "meta": meta or franchise_id,
                "url": reverse("team_detail", args=[franchise_id]),
                "kind": "Team",
            }
        )
    return items


def _detect_country_intent(message):
    patterns = [
        r"(?:players?|who)\s+(?:born in|from)\s+(.+)$",
        r"(?:jogadores?|quem)\s+(?:nascid(?:o|os|a|as)\s+em|de)\s+(.+)$",
        r"(?:mostra|mostrar|lista|listar|quais)\s+(?:os\s+)?jogadores\s+de\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return ""


def _detect_awards_year(message):
    patterns = [
        r"(?:awards?|award winners?)\s+(?:in|for)\s+(\d{4})",
        r"(?:premios|pr[eé]mios|vencedores\s+de\s+pr[eé]mios?)\s+(?:em|de)\s+(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    return ""


def _detect_named_query(message, entity):
    entity_terms = {
        "player": r"player|players|jogador|jogadores",
        "team": r"team|teams|equipa|equipas|equipe|equipes|time|times|clube|clubes|franquia|franquias",
    }

    entity_pattern = entity_terms.get(entity, entity)
    patterns = [
        rf"^(?:find|show|search(?: for)?|look up|mostra|mostrar|procura(?:r)?|pesquisa(?:r)?|encontra(?:r)?)\s+(?:{entity_pattern})\s+(.+)$",
        (
            rf"^(?:who is|open|abrir|abre|dados\s+(?:de|do|da)|info\s+(?:de|do|da)|informacoes\s+(?:de|do|da)|informações\s+(?:de|do|da))\s+(.+)$"
            if entity == "player"
            else rf"^(?:open|abrir|abre)\s+(?:{entity_pattern})\s+(.+)$"
        ),
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1).strip(" ?.")
    return ""


def _fallback_search_term(message):
    cleaned = _fold_text(message)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", cleaned)
    tokens = [token for token in cleaned.split() if token]
    stopwords = {
        "mostra",
        "mostrar",
        "lista",
        "listar",
        "quais",
        "qual",
        "procura",
        "procurar",
        "pesquisa",
        "pesquisar",
        "encontra",
        "encontrar",
        "dados",
        "sobre",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "o",
        "a",
        "os",
        "as",
        "player",
        "players",
        "jogador",
        "jogadores",
        "team",
        "teams",
        "equipa",
        "equipas",
        "time",
        "times",
        "clube",
        "clubes",
        "liga",
        "american",
        "national",
        "league",
        "al",
        "nl",
    }
    meaningful = [token for token in tokens if token not in stopwords]
    return " ".join(meaningful).strip()


def _candidate_search_terms(message):
    normalized = _normalize_message(message)
    folded = _fold_text(normalized)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", folded)
    cleaned = " ".join(cleaned.split())

    terms = []
    for term in [normalized, cleaned, _fallback_search_term(normalized)]:
        term = str(term or "").strip()
        if term and term not in terms:
            terms.append(term)

    tokens = cleaned.split()
    for size in (4, 3, 2):
        if len(tokens) >= size:
            candidate = " ".join(tokens[-size:]).strip()
            if candidate and candidate not in terms:
                terms.append(candidate)

    return terms


def answer_chat_message(message):
    normalized = _normalize_message(message)
    if not normalized:
        return _help_payload()

    league_code = _extract_league_code(normalized)
    lowered = normalized.lower()
    lowered_folded = _fold_text(normalized)

    if "compare" in lowered_folded or "comparar" in lowered_folded:
        return {
            "answer": "Open the comparator to compare two players or two teams. Mixed selections are not allowed.",
            "items": [
                {
                    "label": "Comparator",
                    "meta": "Compare two players or two teams",
                    "url": reverse("compare_players"),
                    "kind": "Page",
                }
            ],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    if league_code and TEAM_KEYWORDS_PATTERN.search(lowered_folded):
        teams = get_teams_by_league_code(league_code)
        league_name = LEAGUE_LABELS.get(league_code, league_code)
        items = [
            {
                "label": league_name,
                "meta": "Open the competition page",
                "url": reverse("league_detail", args=[league_code]),
                "kind": "League",
            }
        ] + _build_team_items(teams)
        return {
            "answer": f"Here are some clubs recorded in the {league_name}.",
            "items": items[:7],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    country = _detect_country_intent(normalized)
    if country:
        players = get_players_by_country(country)
        items = _build_player_items(players)
        return {
            "answer": (
                f'Found {len(items)} player matches from {country}.'
                if items
                else f"I could not find player records from {country}."
            ),
            "items": items or [{"label": "Players", "meta": "Open the player directory", "url": reverse("players"), "kind": "Page"}],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    awards_year = _detect_awards_year(normalized)
    if awards_year:
        awards = get_awards_by_year(awards_year)
        items = []
        for award in awards:
            player_id = award.get("player_id")
            if not player_id:
                continue
            meta = " · ".join(bit for bit in [award.get("award_name"), award.get("league_code")] if bit)
            items.append(
                {
                    "label": award.get("name") or player_id,
                    "meta": meta or awards_year,
                    "url": reverse("player_detail", args=[player_id]),
                    "kind": "Award",
                }
            )
        return {
            "answer": (
                f"Here are award winners from {awards_year}."
                if items
                else f"I could not find award results for {awards_year}."
            ),
            "items": items[:6] or [{"label": "Analytics", "meta": "Open awards and historical views", "url": reverse("analytics"), "kind": "Page"}],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    if SALARY_KEYWORDS_PATTERN.search(lowered_folded):
        leaders = get_salary_leaders()
        items = [
            {
                "label": leader.get("name") or leader.get("player_id"),
                "meta": f'${leader.get("salary", 0):,} · {leader.get("year")}',
                "url": reverse("player_detail", args=[leader.get("player_id")]),
                "kind": "Salary",
            }
            for leader in leaders
            if leader.get("player_id")
        ]
        return {
            "answer": "These are the top salary records in the current dataset.",
            "items": items[:6] or [{"label": "Salaries", "meta": "Open salary leaders", "url": reverse("salaries_list"), "kind": "Page"}],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    player_name = _detect_named_query(normalized, "player")
    if player_name:
        players = find_players_by_name(player_name)
        items = _build_player_items(players)
        return {
            "answer": (
                f'Here are player matches for "{player_name}".'
                if items
                else f'I could not find a player matching "{player_name}".'
            ),
            "items": items or [{"label": "Players", "meta": "Open the player catalog", "url": reverse("players", ) + f"?q={player_name}", "kind": "Page"}],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    team_name = _detect_named_query(normalized, "team")
    if team_name:
        teams = find_teams_by_name(team_name)
        items = _build_team_items(teams)
        return {
            "answer": (
                f'Here are team matches for "{team_name}".'
                if items
                else f'I could not find a team matching "{team_name}".'
            ),
            "items": items or [{"label": "Teams", "meta": "Open the team directory", "url": reverse("teams") + f"?q={team_name}", "kind": "Page"}],
            "suggestions": CHATBOT_SUGGESTIONS,
        }

    # Fallback: try several candidate terms with SPARQL-backed searches.
    for term in _candidate_search_terms(normalized):
        players = find_players_by_name(term)
        if players:
            return {
                "answer": f'Closest player matches for "{normalized}".',
                "items": _build_player_items(players),
                "suggestions": CHATBOT_SUGGESTIONS,
            }

        teams = find_teams_by_name(term)
        if teams:
            return {
                "answer": f'Closest team matches for "{normalized}".',
                "items": _build_team_items(teams),
                "suggestions": CHATBOT_SUGGESTIONS,
            }

    return {
        "answer": "I could not map that question to a known baseball query yet. Try one of the quick prompts below.",
        "items": [
            {"label": "Players", "meta": "Browse player dossiers", "url": reverse("players"), "kind": "Page"},
            {"label": "Teams", "meta": "Browse clubs and leagues", "url": reverse("teams"), "kind": "Page"},
            {"label": "Analytics", "meta": "Awards, salaries, and leaders", "url": reverse("analytics"), "kind": "Page"},
        ],
        "suggestions": CHATBOT_SUGGESTIONS,
    }


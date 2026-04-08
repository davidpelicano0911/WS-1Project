from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from ..sparql import LEAGUE_LABELS, get_players_catalog, get_team_franchise_catalog


def home(request):
    return render(request, "index.html")


def _normalize_search_text(value):
    return " ".join(str(value or "").strip().lower().split())


def _search_rank(query, values):
    normalized_query = _normalize_search_text(query)
    if not normalized_query:
        return None

    normalized_values = [_normalize_search_text(value) for value in values if _normalize_search_text(value)]
    if not normalized_values:
        return None

    for value in normalized_values:
        if value == normalized_query:
            return (0, len(value))

    for value in normalized_values:
        if value.startswith(normalized_query):
            return (1, len(value))

    for value in normalized_values:
        if any(part.startswith(normalized_query) for part in value.split()):
            return (2, len(value))

    for value in normalized_values:
        if normalized_query in value:
            return (3, value.index(normalized_query), len(value))

    return None


def portal_search_view(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"query": query, "players": [], "teams": []})

    player_matches = []
    players = []
    for player in get_players_catalog(search_term=query, limit=40, offset=0):
        rank = _search_rank(
            query,
            [
                player.get("name"),
                " ".join(part for part in [player.get("name_first"), player.get("name_last")] if part),
                player.get("name_first"),
                player.get("name_last"),
                player.get("player_id"),
                player.get("bbref_id"),
            ],
        )
        if rank is None:
            continue
        birth_bits = [bit for bit in [player.get("birth_city"), player.get("birth_country")] if bit]
        meta = " · ".join(
            bit for bit in [player.get("debut"), ", ".join(birth_bits) if birth_bits else ""] if bit
        )
        player_matches.append(
            (
                rank,
                player.get("name") or player.get("player_id", ""),
                {
                    "label": player.get("name") or player.get("player_id"),
                    "meta": meta or player.get("player_id", ""),
                    "url": reverse("player_detail", args=[player.get("player_id", "")]),
                    "kind": "Player",
                },
            )
        )

    seen_franchises = set()
    team_matches = []
    for team in get_team_franchise_catalog():
        rank = _search_rank(
            query,
            [
                team.get("name"),
                team.get("latest_team_name"),
                team.get("latest_park"),
                team.get("franchise_id"),
                team.get("latest_team_id"),
                team.get("latest_team_id_br"),
            ],
        )
        if rank is None:
            continue
        franchise_id = team.get("franchise_id")
        if not franchise_id or franchise_id in seen_franchises:
            continue
        seen_franchises.add(franchise_id)
        league_name = LEAGUE_LABELS.get(team.get("latest_league_code"), team.get("latest_league_code") or "")
        meta_parts = [
            team.get("latest_team_name") or team.get("name"),
            league_name,
            team.get("latest_park"),
        ]
        team_matches.append(
            (
                rank,
                team.get("name") or franchise_id,
                {
                    "label": team.get("name") or franchise_id,
                    "meta": " · ".join(part for part in meta_parts if part),
                    "url": reverse("team_detail", args=[franchise_id]),
                    "kind": "Team",
                },
            )
        )

    player_matches.sort(key=lambda item: (item[0], item[1].lower()))
    team_matches.sort(key=lambda item: (item[0], item[1].lower()))
    players = [item[2] for item in player_matches[:6]]
    teams = [item[2] for item in team_matches[:6]]

    return JsonResponse({"query": query, "players": players, "teams": teams})

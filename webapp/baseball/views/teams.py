from django.http import Http404
from django.shortcuts import render

from ..sparql import get_league_detail, get_teams_by_league, get_league_series_results

ROUND_LABELS = {
    "WS": "World Series",
    "ALCS": "American League Championship Series",
    "NLCS": "National League Championship Series",
    "ALDS1": "American League Division Series 1",
    "ALDS2": "American League Division Series 2",
    "NLDS1": "National League Division Series 1",
    "NLDS2": "National League Division Series 2",
    "ALWC": "American League Wild Card",
    "NLWC": "National League Wild Card",
    "AEDIV": "American League East Division Series",
    "AWDIV": "American League West Division Series",
    "NEDIV": "National League East Division Series",
    "NWDIV": "National League West Division Series",
}


def teams_view(request):
    return render(request, "teams.html")


def _merge_league_team_periods(teams):
    merged = {}
    for team in teams:
        name = (team.get("name") or "Unknown Team").strip()
        bucket = merged.setdefault(
            name,
            {
                "name": name,
                "franchises": set(),
                "park": team.get("park", ""),
                "seasons": 0,
                "first_year": team.get("first_year", 0),
                "last_year": team.get("last_year", 0),
            },
        )

        franchise = (team.get("franchise") or "").strip()
        if franchise:
            bucket["franchises"].add(franchise)

        bucket["seasons"] += team.get("seasons", 0) or 0

        first_year = team.get("first_year", 0) or 0
        last_year = team.get("last_year", 0) or 0
        if bucket["first_year"] == 0 or (first_year and first_year < bucket["first_year"]):
            bucket["first_year"] = first_year
        if last_year >= bucket["last_year"]:
            bucket["last_year"] = last_year
            bucket["park"] = team.get("park", "") or bucket.get("park", "")

    consolidated = []
    for team in merged.values():
        franchises = sorted(team.pop("franchises"))
        team["franchise"] = " / ".join(franchises)
        consolidated.append(team)

    return sorted(consolidated, key=lambda team: (team.get("name", ""), team.get("first_year", 0)))


def _build_league_metrics(league, teams, series_results):
    parks = sorted({team["park"] for team in teams if team.get("park")})
    sorted_teams = sorted(
        teams,
        key=lambda team: (-team.get("seasons", 0), team.get("first_year", 0), team.get("name", "")),
    )
    league_span = max((league.get("last_year", 0) or 0) - (league.get("first_year", 0) or 0) + 1, 1)
    top_teams = []
    for index, team in enumerate(sorted_teams[:6], start=1):
        active_years = max((team.get("last_year", 0) or 0) - (team.get("first_year", 0) or 0) + 1, 1)
        seasons = team.get("seasons", 0) or 0
        share = round((seasons / max(league.get("seasons", 1), 1)) * 100)
        if share >= 85:
            presence_label = "Foundational presence"
        elif share >= 50:
            presence_label = "Long-run contender"
        else:
            presence_label = "Historic chapter"

        enriched_team = {
            **team,
            "rank": index,
            "active_years": active_years,
            "league_share": share,
            "presence_label": presence_label,
            "recent_flag": "Still active at final league year" if team.get("last_year") == league.get("last_year") else "Historic run completed",
            "era_ratio": round((active_years / league_span) * 100),
        }
        top_teams.append(enriched_team)

    world_series = [series for series in series_results if series.get("round") == "WS"]
    playoffs = [series for series in series_results if series.get("round") != "WS"]
    round_breakdown = []
    seen_rounds = {}
    for series in playoffs:
        round_code = series.get("round") or "Unknown"
        bucket = seen_rounds.setdefault(
            round_code,
            {
                "round": round_code,
                "round_label": ROUND_LABELS.get(round_code, round_code),
                "series_count": 0,
                "first_year": None,
                "last_year": None,
                "total_games": 0,
                "internal_series": 0,
                "cross_league_series": 0,
                "latest_winner": "",
                "latest_loser": "",
            },
        )
        bucket["series_count"] += 1
        year = series.get("year")
        if year is not None:
            if bucket["first_year"] is None or year < bucket["first_year"]:
                bucket["first_year"] = year
            if bucket["last_year"] is None or year > bucket["last_year"]:
                bucket["last_year"] = year
                bucket["latest_winner"] = series.get("winner_team_name", "")
                bucket["latest_loser"] = series.get("loser_team_name", "")
        bucket["total_games"] += (series.get("wins") or 0) + (series.get("losses") or 0) + (series.get("ties") or 0)
        if series.get("winner_league") == league["code"] and series.get("loser_league") == league["code"]:
            bucket["internal_series"] += 1
        else:
            bucket["cross_league_series"] += 1

    round_breakdown = sorted(
        seen_rounds.values(),
        key=lambda item: (-item["series_count"], item["round"]),
    )

    recent_series = []
    for series in series_results[:8]:
        wins = series.get("wins") or 0
        losses = series.get("losses") or 0
        ties = series.get("ties") or 0
        scoreline = f"{wins}-{losses}"
        if ties:
            scoreline = f"{scoreline}-{ties}"
        recent_series.append(
            {
                **series,
                "round_label": ROUND_LABELS.get(series.get("round"), series.get("round") or "Unknown round"),
                "scoreline": scoreline,
                "winner_result": "League winner" if series.get("winner_league") == league["code"] else "Opponent winner",
            }
        )

    return {
        "park_count": len(parks),
        "parks": parks,
        "featured_teams": top_teams,
        "world_series_titles": sum(1 for series in world_series if series.get("winner_league") == league["code"]),
        "world_series_runner_up": sum(1 for series in world_series if series.get("loser_league") == league["code"]),
        "playoff_titles": sum(1 for series in playoffs if series.get("winner_league") == league["code"]),
        "playoff_runner_up": sum(1 for series in playoffs if series.get("loser_league") == league["code"]),
        "round_breakdown": round_breakdown,
        "recent_series": recent_series,
    }


def league_detail_view(request, league_code):
    league = get_league_detail(league_code)
    if not league:
        raise Http404("League not found")
    teams_raw = get_teams_by_league(league_code)
    teams = _merge_league_team_periods(teams_raw)
    registry_mode = request.GET.get("registry", "clubs").strip().lower()
    if registry_mode not in {"clubs", "periods"}:
        registry_mode = "clubs"
    registry_search = request.GET.get("team", "").strip()
    registry_franchise = request.GET.get("franchise", "").strip().upper()
    registry_franchises = sorted({(team.get("franchise") or "").strip() for team in teams_raw if (team.get("franchise") or "").strip()})

    if registry_mode == "clubs":
        registry_teams = teams
    else:
        registry_teams = teams_raw
        if registry_search:
            search_term = registry_search.lower()
            registry_teams = [team for team in registry_teams if search_term in (team.get("name") or "").lower()]
        if registry_franchise:
            registry_teams = [team for team in registry_teams if (team.get("franchise") or "").strip().upper() == registry_franchise]

    all_series = get_league_series_results(league_code)
    world_series = [s for s in all_series if s["round"] == "WS"]
    playoffs = [s for s in all_series if s["round"] != "WS"]
    metrics = _build_league_metrics(league, teams, all_series)

    context = {
        "league": league,
        "teams": teams,
        "teams_raw": teams_raw,
        "registry_mode": registry_mode,
        "registry_teams": registry_teams,
        "registry_club_count": len(teams),
        "registry_period_count": len(teams_raw),
        "registry_search": registry_search,
        "registry_franchise": registry_franchise,
        "registry_franchises": registry_franchises,
        "world_series": world_series,
        "playoffs": playoffs,
        "series_results": all_series,
        **metrics,
    }
    return render(request, "league_detail.html", context)

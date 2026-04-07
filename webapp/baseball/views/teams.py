from django.http import Http404
from django.shortcuts import render

from ..sparql import get_league_detail, get_teams_by_league, get_league_series_results


def teams_view(request):
    return render(request, "teams.html")


def league_detail_view(request, league_code):
    league = get_league_detail(league_code)
    if not league:
        raise Http404("League not found")
    all_series = get_league_series_results(league_code)
    world_series = [s for s in all_series if s["round"] == "WS"]
    playoffs = [s for s in all_series if s["round"] != "WS"]

    context = {
        "league": league,
        "teams": get_teams_by_league(league_code),
        "world_series": world_series,
        "playoffs": playoffs,
        "series_results": all_series,
    }
    return render(request, "league_detail.html", context)

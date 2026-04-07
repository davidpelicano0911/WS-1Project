from django.http import Http404
from django.shortcuts import render

from ..sparql import get_league_detail, get_teams_by_league


def teams_view(request):
    return render(request, "teams.html")


def league_detail_view(request, league_code):
    league = get_league_detail(league_code)
    if not league:
        raise Http404("League not found")

    context = {
        "league": league,
        "teams": get_teams_by_league(league_code),
    }
    return render(request, "league_detail.html", context)

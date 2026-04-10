from django.shortcuts import render

from ..sparql import (
    get_awards_list,
    get_top_salaries,
    get_hall_of_fame_members,
    get_managers_list
)

from ..sparql_queries.misc import get_global_player_leaders, get_global_team_leaders

def analytics_view(request):
    context = {
        "global_batting": get_global_player_leaders(),
        "global_teams": get_global_team_leaders(),
        "salaries": get_top_salaries(),
        "awards": get_awards_list(),
        "members": get_hall_of_fame_members(),
        "managers": get_managers_list()[:50]  # Limiting managers to avoid giant list in tab
    }
    return render(request, "analytics.html", context)


# Keep these around if any legacy routes still need them temporarily hookups
def awards_view(request):
    awards = get_awards_list()
    return render(request, "awards.html", {"awards": awards})


def salaries_view(request):
    salaries = get_top_salaries()
    return render(request, "salaries.html", {"salaries": salaries})


def hall_of_fame_view(request):
    members = get_hall_of_fame_members()
    return render(request, "hall_of_fame.html", {"members": members})


def managers_view(request):
    managers = get_managers_list()
    return render(request, "managers.html", {"managers": managers})

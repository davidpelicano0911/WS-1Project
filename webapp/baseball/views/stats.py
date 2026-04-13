from django.shortcuts import render

from ..sparql import (
    get_awards_list,
    get_hall_of_fame_members,
    get_managers_list,
    get_top_salaries,
)

from ..sparql_queries.misc import (
    get_award_league_options,
    get_award_options,
    get_award_year_options,
    get_awards_catalog,
    get_awards_timeline,
    get_franchise_history,
    get_franchise_options,
    get_global_player_leaders,
    get_global_team_leaders,
    get_hall_of_fame_timeline,
    get_salary_trends,
)


def _get_default_franchise_id(global_teams, franchise_options):
    available = {option["franch_id"] for option in franchise_options if option.get("franch_id")}
    for team in global_teams:
        franch_id = team.get("franch_id")
        if franch_id in available:
            return franch_id
    return franchise_options[0]["franch_id"] if franchise_options else ""


def analytics_view(request):
    global_teams = get_global_team_leaders()
    franchise_options = get_franchise_options()

    context = {
        "global_batting": get_global_player_leaders(),
        "global_teams": global_teams,
        "salaries": get_top_salaries(),
        "salary_trends": get_salary_trends(),
        "franchise_history": get_franchise_history(),
        "franchise_options": franchise_options,
        "default_franchise_id": _get_default_franchise_id(global_teams, franchise_options),
        "awards": get_awards_list(),
        "awards_catalog": get_awards_catalog(),
        "awards_timeline": get_awards_timeline(),
        "award_year_options": get_award_year_options(),
        "award_options": get_award_options(),
        "league_options": get_award_league_options(),
        "members": get_hall_of_fame_members(),
        "hall_timeline": get_hall_of_fame_timeline(),
        "managers": get_managers_list()[:50],  # Limiting managers to avoid giant list in tab
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

from django.shortcuts import render

from ..sparql import get_awards_list, get_top_salaries, get_hall_of_fame_members, get_managers_list


def analytics_view(request):
    return render(request, "analytics.html")


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

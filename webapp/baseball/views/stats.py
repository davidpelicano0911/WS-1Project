from django.shortcuts import render

from ..sparql import get_awards_list, get_top_salaries


def analytics_view(request):
    return render(request, "analytics.html")


def awards_view(request):
    awards = get_awards_list()
    return render(request, "awards.html", {"awards": awards})


def salaries_view(request):
    salaries = get_top_salaries()
    return render(request, "salaries.html", {"salaries": salaries})


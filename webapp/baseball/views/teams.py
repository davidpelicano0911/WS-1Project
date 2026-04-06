from django.shortcuts import render


def teams_view(request):
    return render(request, "teams.html")

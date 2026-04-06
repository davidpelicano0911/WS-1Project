from .team_branding import get_header_teams


def header_teams(request):
    return {"header_teams": get_header_teams()}

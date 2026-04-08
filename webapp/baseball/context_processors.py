from .compare_selection import get_compare_selection
from .sparql import get_header_leagues_graph
from .team_branding import get_header_teams


def header_teams(request):
    return {"header_teams": get_header_teams()}


def header_leagues(request):
    return {"header_leagues": get_header_leagues_graph()}


def compare_selection(request):
    return {"compare_selection": get_compare_selection(request)}

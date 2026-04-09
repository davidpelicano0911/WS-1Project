from .forms import LoginForm, RegisterForm
from .compare_selection import get_compare_selection
from .sparql import get_header_leagues_graph
from .team_branding import get_header_teams


def header_teams(request):
    try:
        teams = get_header_teams()
    except Exception:
        teams = []
    return {"header_teams": teams}


def header_leagues(request):
    try:
        leagues = get_header_leagues_graph()
    except Exception:
        leagues = []
    return {"header_leagues": leagues}


def compare_selection(request):
    return {"compare_selection": get_compare_selection(request)}


def auth_forms(request):
    if request.user.is_authenticated:
        return {}

    next_url = request.get_full_path()
    if request.path in {"/login/", "/register/"}:
        next_url = "/"

    return {
        "modal_login_form": LoginForm(prefix="login"),
        "modal_register_form": RegisterForm(prefix="register"),
        "auth_modal_next_url": next_url,
    }

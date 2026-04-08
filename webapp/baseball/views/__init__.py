from .about import about_view
from .auth import login_view, logout_view, register_view
from .home import home, portal_search_view
from .quiz import quiz_answer_api_view, quiz_start_api_view, quiz_state_api_view, quiz_view
from .teams import league_detail_view, team_detail_view, teams_view
from .players import compare_players_view, compare_selection_view, graph_view, player_detail_view, players_view
from .stats import analytics_view, awards_view, salaries_view
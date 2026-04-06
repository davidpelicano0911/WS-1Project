from django.shortcuts import render

from ..sparql import (
    get_player_graph_data,
    get_player_options_by_initial,
    get_player_summary,
)


def _alphabet():
    return [chr(code) for code in range(ord("A"), ord("Z") + 1)]


def players_view(request):
    return render(request, "players.html")


def compare_players_view(request):
    letters = _alphabet()
    player1_letter = request.GET.get("player1_letter", "").strip().upper()
    player2_letter = request.GET.get("player2_letter", "").strip().upper()
    player1_term = request.GET.get("player1", "").strip()
    player2_term = request.GET.get("player2", "").strip()
    player1_options = get_player_options_by_initial(player1_letter) if player1_letter in letters else []
    player2_options = get_player_options_by_initial(player2_letter) if player2_letter in letters else []

    player1 = get_player_summary(player1_term) if player1_term else None
    player2 = get_player_summary(player2_term) if player2_term else None

    context = {
        "letters": letters,
        "player1_letter": player1_letter,
        "player2_letter": player2_letter,
        "player1": player1,
        "player2": player2,
        "player1_term": player1_term,
        "player2_term": player2_term,
        "player1_options": player1_options,
        "player2_options": player2_options,
        "submitted": bool(player1_term or player2_term),
        "player1_missing": bool(player1_term and not player1),
        "player2_missing": bool(player2_term and not player2),
    }
    return render(request, "compare.html", context)


def graph_view(request):
    letters = _alphabet()
    player_letter = request.GET.get("player_letter", "").strip().upper()
    player_term = request.GET.get("player", "").strip()
    player_options = get_player_options_by_initial(player_letter) if player_letter in letters else []
    player = get_player_summary(player_term) if player_term else None
    graph_data = get_player_graph_data(player_term) if player_term else {"nodes": [], "edges": []}

    context = {
        "letters": letters,
        "player_letter": player_letter,
        "player_term": player_term,
        "player_options": player_options,
        "player": player,
        "graph_nodes": graph_data["nodes"],
        "graph_edges": graph_data["edges"],
    }
    return render(request, "graph.html", context)


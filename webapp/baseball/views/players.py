from django.shortcuts import render

from ..sparql import (
    get_player_allstar_history,
    get_player_award_history,
    get_player_batting_seasons,
    get_player_batting_summary,
    get_player_graph_data,
    get_player_hall_of_fame,
    get_player_options_by_initial,
    get_player_pitching_seasons,
    get_player_pitching_summary,
    get_player_salary_history,
    get_player_summary,
    get_player_team_history,
)


def _alphabet():
    return [chr(code) for code in range(ord("A"), ord("Z") + 1)]


def _player_label(player):
    if not player:
        return ""
    return f"{player['name']} ({player['player_id']})"


def _to_int(value, default=0):
    if value in (None, "", "N/A"):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _year_from_date(value):
    if not value or value == "N/A":
        return None
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _format_number(value):
    if value is None:
        return "N/A"
    return f"{int(value):,}"


def _format_currency(value):
    if value is None:
        return "N/A"
    return f"${int(value):,}"


def _format_rate(value, digits=3):
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def _format_era(value):
    return _format_rate(value, digits=2)


def _format_ip_outs(value):
    if value is None:
        return "N/A"
    whole = int(value) // 3
    remainder = int(value) % 3
    return f"{whole}.{remainder}"


def _format_yes_no(value):
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


def _format_text(value, default="N/A"):
    if value in (None, ""):
        return default
    return str(value)


def _summarize_values(values, limit=4):
    if not values:
        return "No overlap yet"
    values = [str(value) for value in values if value]
    if not values:
        return "No overlap yet"
    if len(values) <= limit:
        return ", ".join(values)
    return f"{', '.join(values[:limit])} +{len(values) - limit} more"


def _build_compare_row(
    label,
    player1_value,
    player2_value,
    *,
    display_formatter=_format_number,
    delta_formatter=None,
    better="higher",
    note="",
):
    player1_display = display_formatter(player1_value)
    player2_display = display_formatter(player2_value)

    winner_side = "none"
    winner_display = "N/A"
    delta_display = "Need both values"

    if better == "boolean":
        left = None if player1_value is None else bool(player1_value)
        right = None if player2_value is None else bool(player2_value)
        player1_display = _format_yes_no(left)
        player2_display = _format_yes_no(right)

        if left is None and right is None:
            pass
        elif left == right:
            winner_side = "tie"
            winner_display = "Tie"
            delta_display = "Shared" if left else "Neither"
        else:
            winner_side = "player1" if left else "player2"
            winner_display = "Player 1" if left else "Player 2"
            delta_display = "Yes vs No"
        return {
            "label": label,
            "note": note,
            "player1_display": player1_display,
            "player2_display": player2_display,
            "winner_side": winner_side,
            "winner_display": winner_display,
            "delta_display": delta_display,
        }

    left = player1_value
    right = player2_value

    if left is None and right is None:
        pass
    elif right is None:
        winner_side = "player1"
        winner_display = "Player 1"
        delta_display = "Only player with data"
    elif left is None:
        winner_side = "player2"
        winner_display = "Player 2"
        delta_display = "Only player with data"
    elif abs(left - right) < 1e-9:
        winner_side = "tie"
        winner_display = "Tie"
        delta_display = "Even"
    else:
        player1_wins = left < right if better == "lower" else left > right
        winner_side = "player1" if player1_wins else "player2"
        winner_display = "Player 1" if player1_wins else "Player 2"
        delta_value = abs(left - right)
        formatter = delta_formatter or display_formatter
        formatted_gap = formatter(delta_value)
        delta_display = formatted_gap if formatted_gap.startswith("+") else f"+{formatted_gap}"

    return {
        "label": label,
        "note": note,
        "player1_display": player1_display,
        "player2_display": player2_display,
        "winner_side": winner_side,
        "winner_display": winner_display,
        "delta_display": delta_display,
    }


def _best_line(lines, key, *, higher=True, require=None):
    candidates = []
    for line in lines:
        if require and not require(line):
            continue
        value = line.get(key)
        if value is None:
            continue
        candidates.append(line)

    if not candidates:
        return None

    if higher:
        return max(candidates, key=lambda line: (line.get(key, 0), line.get("year", 0)))
    return min(
        candidates,
        key=lambda line: (line.get(key), -(line.get("innings_outs") or 0), line.get("year", 0)),
    )


def _build_best_season_entry(line, title, key, formatter, suffix=""):
    if not line:
        return None
    display = formatter(line.get(key))
    if suffix and display != "N/A":
        display = f"{display} {suffix}"
    return {
        "title": title,
        "value": line.get(key),
        "display": display,
        "detail": f"{line.get('year', 'N/A')} · {line.get('team_label', line.get('team_name', 'Unknown team'))}",
    }


def _build_player_timeline(profile):
    items = []

    if profile.get("debut"):
        items.append({"label": "Debut", "value": profile["debut"]})
    if profile.get("first_season"):
        items.append({"label": "First season", "value": str(profile["first_season"])})
    if profile.get("peak_salary_entry"):
        items.append(
            {
                "label": "Peak salary",
                "value": profile["peak_salary_entry"]["display"],
                "detail": profile["peak_salary_entry"]["detail"],
            }
        )
    if profile.get("best_hr_entry"):
        items.append(
            {
                "label": "Best HR season",
                "value": profile["best_hr_entry"]["display"],
                "detail": profile["best_hr_entry"]["detail"],
            }
        )
    if profile.get("best_rbi_entry"):
        items.append(
            {
                "label": "Best RBI season",
                "value": profile["best_rbi_entry"]["display"],
                "detail": profile["best_rbi_entry"]["detail"],
            }
        )
    if profile.get("best_era_entry"):
        items.append(
            {
                "label": "Lowest ERA season",
                "value": profile["best_era_entry"]["display"],
                "detail": profile["best_era_entry"]["detail"],
            }
        )
    if profile["hall_of_fame"].get("inducted_year"):
        items.append({"label": "Hall of Fame", "value": str(profile["hall_of_fame"]["inducted_year"])})
    if profile.get("latest_award_year"):
        items.append({"label": "Latest award", "value": str(profile["latest_award_year"])})
    if profile.get("final_game"):
        items.append({"label": "Final game", "value": profile["final_game"]})

    return items


def _build_profile_card_stats(profile):
    return [
        {"label": "Birth year", "value": _format_text(profile.get("birth_year"))},
        {"label": "Birth country", "value": _format_text(profile.get("birth_country"))},
        {
            "label": "Bats / throws",
            "value": f"{_format_text(profile.get('bats'))} / {_format_text(profile.get('throws'))}",
        },
        {"label": "Debut", "value": _format_text(profile.get("debut"))},
        {"label": "Final game", "value": _format_text(profile.get("final_game"))},
        {"label": "Seasons", "value": _format_number(profile.get("career_seasons", 0))},
        {"label": "Peak salary", "value": _format_currency(profile.get("peak_salary"))},
        {"label": "Awards", "value": _format_number(profile.get("award_count_total", 0))},
    ]


def _build_compare_profile(player_id):
    summary = get_player_summary(player_id)
    if not summary:
        return None

    batting_seasons = get_player_batting_seasons(player_id)
    pitching_seasons = get_player_pitching_seasons(player_id)
    batting_summary = get_player_batting_summary(player_id)
    pitching_summary = get_player_pitching_summary(player_id)
    award_history = get_player_award_history(player_id)
    allstar_history = get_player_allstar_history(player_id)
    hall_of_fame = get_player_hall_of_fame(player_id)
    salary_history = get_player_salary_history(player_id)
    team_history = get_player_team_history(player_id)

    season_years = sorted({entry["year"] for entry in team_history if entry.get("year")})
    if not season_years:
        first_year = _year_from_date(summary.get("debut"))
        last_year = _year_from_date(summary.get("final_game"))
        if first_year:
            season_years = list(range(first_year, (last_year or first_year) + 1))

    team_names = sorted({entry["team_name"] for entry in team_history if entry.get("team_name")})
    franchise_names = sorted({entry["franchise_name"] for entry in team_history if entry.get("franchise_name")})
    league_names = sorted({entry["league"] for entry in team_history if entry.get("league")})

    award_years = sorted({award["year"] for award in award_history if award.get("year")})
    award_types = sorted({award["award_name"] for award in award_history if award.get("award_name")})
    allstar_years = sorted({appearance["year"] for appearance in allstar_history if appearance.get("year")})

    peak_salary_line = max(
        salary_history,
        key=lambda entry: (entry.get("salary", 0), entry.get("year") or 0),
        default=None,
    )
    peak_salary_entry = (
        {
            "title": "Highest salary season",
            "value": peak_salary_line["salary"],
            "display": _format_currency(peak_salary_line["salary"]),
            "detail": f"{peak_salary_line.get('year', 'N/A')} · {peak_salary_line.get('team_name') or 'Unknown team'}",
        }
        if peak_salary_line
        else None
    )

    best_hr_entry = _build_best_season_entry(
        _best_line(batting_seasons, "home_runs", higher=True),
        "Best HR season",
        "home_runs",
        _format_number,
        "HR",
    )
    best_rbi_entry = _build_best_season_entry(
        _best_line(batting_seasons, "rbi", higher=True),
        "Best RBI season",
        "rbi",
        _format_number,
        "RBI",
    )
    best_era_entry = _build_best_season_entry(
        _best_line(pitching_seasons, "era", higher=False),
        "Lowest ERA season",
        "era",
        _format_era,
        "ERA",
    )

    profile = {
        **summary,
        "batting_seasons_detail": batting_seasons,
        "pitching_seasons_detail": pitching_seasons,
        "batting_summary": batting_summary,
        "pitching_summary": pitching_summary,
        "award_history": award_history,
        "allstar_history": allstar_history,
        "allstar_count": len(allstar_history),
        "allstar_years": allstar_years,
        "hall_of_fame": hall_of_fame,
        "salary_history": salary_history,
        "team_history": team_history,
        "season_years": season_years,
        "career_seasons": len(season_years),
        "career_span_years": (season_years[-1] - season_years[0] + 1) if season_years else None,
        "first_season": season_years[0] if season_years else None,
        "last_season": season_years[-1] if season_years else None,
        "team_names": team_names,
        "team_count": len(team_names),
        "franchise_names": franchise_names,
        "franchise_count": len(franchise_names),
        "league_names": league_names,
        "league_count": len(league_names),
        "award_count_total": len(award_history),
        "award_type_count": len(award_types),
        "award_types": award_types,
        "first_award_year": award_years[0] if award_years else None,
        "latest_award_year": award_years[-1] if award_years else None,
        "peak_salary": peak_salary_line["salary"] if peak_salary_line else _to_int(summary.get("max_salary"), None),
        "peak_salary_entry": peak_salary_entry,
        "best_hr_entry": best_hr_entry,
        "best_rbi_entry": best_rbi_entry,
        "best_era_entry": best_era_entry,
    }
    profile["card_stats"] = _build_profile_card_stats(profile)
    profile["timeline_items"] = _build_player_timeline(profile)
    profile["recent_awards"] = [
        {
            "label": str(item["year"]) if item.get("year") else "Award",
            "value": item["award_name"],
            "detail": item["league"],
        }
        for item in reversed(award_history[-6:])
    ]
    profile["allstar_items"] = [
        {"label": str(year), "value": "All-Star appearance"}
        for year in reversed(allstar_years[-6:])
    ]
    return profile


def _build_shared_context(player1, player2):
    shared_teams = sorted(set(player1["team_names"]) & set(player2["team_names"]))
    shared_franchises = sorted(set(player1["franchise_names"]) & set(player2["franchise_names"]))
    shared_leagues = sorted(set(player1["league_names"]) & set(player2["league_names"]))
    overlap_years = sorted(set(player1["season_years"]) & set(player2["season_years"]))

    overlap_detail = _summarize_values(overlap_years, limit=6)
    if overlap_years:
        overlap_detail = f"{overlap_years[0]}-{overlap_years[-1]}" if len(overlap_years) > 1 else str(overlap_years[0])

    return [
        {
            "title": "Shared teams",
            "value": _format_number(len(shared_teams)),
            "detail": _summarize_values(shared_teams),
        },
        {
            "title": "Overlapping seasons",
            "value": _format_number(len(overlap_years)),
            "detail": overlap_detail,
        },
        {
            "title": "Common franchises",
            "value": _format_number(len(shared_franchises)),
            "detail": _summarize_values(shared_franchises),
        },
        {
            "title": "Shared leagues",
            "value": _format_number(len(shared_leagues)),
            "detail": _summarize_values(shared_leagues),
        },
    ]


def _build_best_season_cards(player1, player2):
    def _season_compare_card(title, player1_entry, player2_entry, *, better="higher", delta_formatter=_format_number):
        if not player1_entry and not player2_entry:
            return None

        player1_value = player1_entry["value"] if player1_entry else None
        player2_value = player2_entry["value"] if player2_entry else None
        row = _build_compare_row(
            title,
            player1_value,
            player2_value,
            display_formatter=lambda value: "N/A" if value is None else str(value),
            delta_formatter=delta_formatter,
            better=better,
        )

        return {
            "title": title,
            "winner_side": row["winner_side"],
            "winner_display": row["winner_display"],
            "delta_display": row["delta_display"],
            "player1_display": player1_entry["display"] if player1_entry else "N/A",
            "player1_detail": player1_entry["detail"] if player1_entry else "No season available",
            "player2_display": player2_entry["display"] if player2_entry else "N/A",
            "player2_detail": player2_entry["detail"] if player2_entry else "No season available",
        }

    cards = [
        _season_compare_card(
            "Best HR season",
            player1.get("best_hr_entry"),
            player2.get("best_hr_entry"),
            delta_formatter=_format_number,
        ),
        _season_compare_card(
            "Best RBI season",
            player1.get("best_rbi_entry"),
            player2.get("best_rbi_entry"),
            delta_formatter=_format_number,
        ),
        _season_compare_card(
            "Highest salary season",
            player1.get("peak_salary_entry"),
            player2.get("peak_salary_entry"),
            delta_formatter=_format_currency,
        ),
        _season_compare_card(
            "Lowest ERA season",
            player1.get("best_era_entry"),
            player2.get("best_era_entry"),
            better="lower",
            delta_formatter=_format_era,
        ),
    ]
    return [card for card in cards if card]


def _build_compare_tabs(player1, player2):
    career_rows = [
        _build_compare_row("Seasons played", player1["career_seasons"], player2["career_seasons"]),
        _build_compare_row("Career span", player1["career_span_years"], player2["career_span_years"]),
        _build_compare_row("Teams played for", player1["team_count"], player2["team_count"]),
        _build_compare_row("Franchises represented", player1["franchise_count"], player2["franchise_count"]),
        _build_compare_row("Leagues played in", player1["league_count"], player2["league_count"]),
        _build_compare_row(
            "Peak salary",
            player1["peak_salary"],
            player2["peak_salary"],
            display_formatter=_format_currency,
            delta_formatter=_format_currency,
        ),
    ]

    batting_rows = [
        _build_compare_row("Games", player1["batting_summary"]["games"], player2["batting_summary"]["games"]),
        _build_compare_row("At-bats", player1["batting_summary"]["at_bats"], player2["batting_summary"]["at_bats"]),
        _build_compare_row("Hits", player1["batting_summary"]["hits"], player2["batting_summary"]["hits"]),
        _build_compare_row("Runs", player1["batting_summary"]["runs"], player2["batting_summary"]["runs"]),
        _build_compare_row("Home runs", player1["batting_summary"]["home_runs"], player2["batting_summary"]["home_runs"]),
        _build_compare_row("RBI", player1["batting_summary"]["rbi"], player2["batting_summary"]["rbi"]),
        _build_compare_row(
            "Stolen bases",
            player1["batting_summary"]["stolen_bases"],
            player2["batting_summary"]["stolen_bases"],
        ),
        _build_compare_row(
            "AVG",
            player1["batting_summary"]["avg"],
            player2["batting_summary"]["avg"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
        _build_compare_row(
            "OBP",
            player1["batting_summary"]["obp"],
            player2["batting_summary"]["obp"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
        _build_compare_row(
            "SLG",
            player1["batting_summary"]["slg"],
            player2["batting_summary"]["slg"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
        _build_compare_row(
            "OPS",
            player1["batting_summary"]["ops"],
            player2["batting_summary"]["ops"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
        _build_compare_row(
            "BB / K",
            player1["batting_summary"]["bb_k_ratio"],
            player2["batting_summary"]["bb_k_ratio"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
        _build_compare_row(
            "HR per season",
            player1["batting_summary"]["hr_per_season"],
            player2["batting_summary"]["hr_per_season"],
            display_formatter=_format_rate,
            delta_formatter=_format_rate,
        ),
    ]

    pitching_rows = [
        _build_compare_row("Pitching seasons", player1["pitching_summary"]["seasons"], player2["pitching_summary"]["seasons"]),
        _build_compare_row("Wins", player1["pitching_summary"]["wins"], player2["pitching_summary"]["wins"]),
        _build_compare_row(
            "Losses",
            player1["pitching_summary"]["losses"],
            player2["pitching_summary"]["losses"],
            better="lower",
            note="Lower is better.",
        ),
        _build_compare_row(
            "ERA",
            player1["pitching_summary"]["era"],
            player2["pitching_summary"]["era"],
            display_formatter=_format_era,
            delta_formatter=_format_era,
            better="lower",
            note="Lower is better.",
        ),
        _build_compare_row(
            "Strikeouts",
            player1["pitching_summary"]["strikeouts"],
            player2["pitching_summary"]["strikeouts"],
        ),
        _build_compare_row("Saves", player1["pitching_summary"]["saves"], player2["pitching_summary"]["saves"]),
        _build_compare_row(
            "Games started",
            player1["pitching_summary"]["games_started"],
            player2["pitching_summary"]["games_started"],
        ),
        _build_compare_row(
            "Innings pitched",
            player1["pitching_summary"]["innings_outs"],
            player2["pitching_summary"]["innings_outs"],
            display_formatter=_format_ip_outs,
            delta_formatter=_format_ip_outs,
        ),
    ]

    awards_rows = [
        _build_compare_row("Awards won", player1["award_count_total"], player2["award_count_total"]),
        _build_compare_row("Award types", player1["award_type_count"], player2["award_type_count"]),
        _build_compare_row("All-Star appearances", player1["allstar_count"], player2["allstar_count"]),
        _build_compare_row(
            "Hall of Fame inducted",
            player1["hall_of_fame"]["inducted"],
            player2["hall_of_fame"]["inducted"],
            better="boolean",
        ),
    ]

    timeline_cards = _build_shared_context(player1, player2)

    tabs = [
        {
            "id": "career",
            "label": "Career",
            "icon": "bi-bar-chart-line-fill",
            "description": "Career-level footprint across seasons, teams, and earnings.",
            "rows": career_rows,
        },
        {
            "id": "batting",
            "label": "Batting",
            "icon": "bi-bullseye",
            "description": "Regular-season batting totals plus rate production.",
            "rows": batting_rows,
        },
        {
            "id": "pitching",
            "label": "Pitching",
            "icon": "bi-activity",
            "description": "Pitcher-aware head-to-head view using regular-season pitching records.",
            "rows": pitching_rows,
        },
        {
            "id": "awards",
            "label": "Awards",
            "icon": "bi-trophy-fill",
            "description": "Accolades, All-Star recognition, and Hall of Fame status.",
            "rows": awards_rows,
            "player1_aside_title": "Recent awards",
            "player1_aside_entries": player1["recent_awards"] or player1["allstar_items"],
            "player2_aside_title": "Recent awards",
            "player2_aside_entries": player2["recent_awards"] or player2["allstar_items"],
        },
        {
            "id": "timeline",
            "label": "Timeline",
            "icon": "bi-clock-history",
            "description": "Shared context plus player-specific milestones and peak seasons.",
            "rows": [],
            "pair_cards": timeline_cards,
            "player1_aside_title": "Career timeline",
            "player1_aside_entries": player1["timeline_items"],
            "player2_aside_title": "Career timeline",
            "player2_aside_entries": player2["timeline_items"],
        },
    ]

    filtered_tabs = []
    for tab in tabs:
        has_rows = bool(tab.get("rows"))
        has_pair_cards = bool(tab.get("pair_cards"))
        has_player_entries = bool(tab.get("player1_aside_entries") or tab.get("player2_aside_entries"))
        if tab["id"] == "pitching" and not (
            player1["pitching_summary"]["seasons"] or player2["pitching_summary"]["seasons"]
        ):
            continue
        if tab["id"] == "awards" and not (
            player1["award_count_total"]
            or player2["award_count_total"]
            or player1["allstar_count"]
            or player2["allstar_count"]
            or player1["hall_of_fame"]["vote_count"]
            or player2["hall_of_fame"]["vote_count"]
        ):
            continue
        if has_rows or has_pair_cards or has_player_entries:
            filtered_tabs.append(tab)

    return filtered_tabs


def _build_compare_scoreboard(tabs):
    player1_wins = 0
    player2_wins = 0
    ties = 0

    for tab in tabs:
        for row in tab.get("rows", []):
            if row["winner_side"] == "player1":
                player1_wins += 1
            elif row["winner_side"] == "player2":
                player2_wins += 1
            elif row["winner_side"] == "tie":
                ties += 1

    return {
        "player1_wins": player1_wins,
        "player2_wins": player2_wins,
        "ties": ties,
        "decisive_metrics": player1_wins + player2_wins,
    }


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

    player1 = _build_compare_profile(player1_term) if player1_term else None
    player2 = _build_compare_profile(player2_term) if player2_term else None
    compare_ready = bool(player1 and player2)
    compare_tabs = _build_compare_tabs(player1, player2) if compare_ready else []
    compare_scoreboard = _build_compare_scoreboard(compare_tabs) if compare_tabs else None
    best_season_cards = _build_best_season_cards(player1, player2) if compare_ready else []

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
        "player1_selected_label": _player_label(player1),
        "player2_selected_label": _player_label(player2),
        "compare_ready": compare_ready,
        "compare_tabs": compare_tabs,
        "compare_scoreboard": compare_scoreboard,
        "best_season_cards": best_season_cards,
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
        "player_selected_label": _player_label(player),
        "player": player,
        "graph_nodes": graph_data["nodes"],
        "graph_edges": graph_data["edges"],
    }
    return render(request, "graph.html", context)

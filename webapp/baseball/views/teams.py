from concurrent.futures import ThreadPoolExecutor

from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse

from ..sparql import (
    DIVISION_LABELS,
    LEAGUE_LABELS,
    get_league_detail,
    get_league_series_results,
    get_team_all_stars,
    get_team_awards,
    get_team_batting_roster,
    get_team_franchise_catalog,
    get_team_history,
    get_team_managers,
    get_team_pitching_roster,
    get_team_postseason_history,
    get_teams_by_league,
)
from ..team_branding import MLB_LOGO_IDS, TEAM_CODE_NORMALIZATION


def _to_int(value, default=0):
    if value in (None, "", "N/A"):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _format_number(value, default="N/A"):
    if value in (None, "", "N/A"):
        return default
    return f"{int(value):,}"


def _format_rate(value, digits=3, baseball_style=False, default="N/A"):
    if value in (None, "", "N/A"):
        return default

    text = f"{float(value):.{digits}f}"
    if baseball_style:
        if text.startswith("0"):
            return text[1:]
        if text.startswith("-0"):
            return f"-{text[2:]}"
        return text
    return text


def _format_percentage(value, digits=1, default="N/A"):
    if value in (None, "", "N/A"):
        return default
    return f"{float(value) * 100:.{digits}f}%"


def _format_record(wins, losses):
    return f"{_format_number(wins, '0')}-{_format_number(losses, '0')}"


def _format_innings(value):
    if value in (None, "", "N/A"):
        return "N/A"
    whole = int(value) // 3
    remainder = int(value) % 3
    return f"{whole}.{remainder}"


def _league_display(code):
    return LEAGUE_LABELS.get(code, code or "Unknown league")


def _division_display(code):
    return DIVISION_LABELS.get(code, code or "No division")


def _normalized_team_code(*codes):
    for code in codes:
        text = str(code or "").strip().upper()
        if not text:
            continue
        normalized = TEAM_CODE_NORMALIZATION.get(text, text)
        if normalized:
            return normalized
    return ""


def _team_logo_id(*codes):
    normalized = _normalized_team_code(*codes)
    return MLB_LOGO_IDS.get(normalized)


def _season_badges(team):
    badges = []
    if team.get("world_series_winner"):
        badges.append({"label": "World Series winner", "tone": "gold", "icon": "bi-trophy-fill"})
    if team.get("league_winner"):
        badges.append({"label": "League champion", "tone": "blue", "icon": "bi-stars"})
    if team.get("division_winner"):
        badges.append({"label": "Division winner", "tone": "blue", "icon": "bi-flag-fill"})
    if team.get("wild_card_winner"):
        badges.append({"label": "Wild card", "tone": "neutral", "icon": "bi-ticket-perforated-fill"})
    if not badges and team.get("rank") == 1:
        badges.append({"label": "First place finish", "tone": "neutral", "icon": "bi-award-fill"})
    return badges


def _season_outcome(team, postseason_rows):
    if team.get("world_series_winner"):
        return "Won the World Series"
    if team.get("league_winner"):
        return "Reached the World Series"
    if postseason_rows:
        deepest_round = postseason_rows[0].get("round") or "postseason"
        return f"Reached the {deepest_round}"
    if team.get("wild_card_winner"):
        return "Reached the postseason via wild card"
    if team.get("division_winner"):
        return "Won the division"
    return "No postseason run recorded"


def _catalog_badges(entry):
    badges = []
    if entry.get("latest_world_series_winner"):
        badges.append("World Series")
    elif entry.get("latest_league_winner"):
        badges.append("League champs")
    elif entry.get("latest_division_winner"):
        badges.append("Division winners")
    elif entry.get("latest_wild_card_winner"):
        badges.append("Wild card")
    if entry.get("active"):
        badges.append("Active")
    return badges[:2]


def _build_franchise_profile(history, catalog_entry):
    seasons = len(history)
    total_wins = sum(_to_int(season.get("wins"), 0) for season in history)
    total_losses = sum(_to_int(season.get("losses"), 0) for season in history)
    total_games = total_wins + total_losses
    parks = {season.get("park") for season in history if season.get("park")}
    leagues = {season.get("league_code") for season in history if season.get("league_code")}
    names = {season.get("team_name") for season in history if season.get("team_name")}
    profile = [
        {
            "label": "Franchise span",
            "value": f"{catalog_entry['first_year']} - {catalog_entry['last_year']}",
            "detail": "First and last recorded seasons in the archive.",
        },
        {
            "label": "Seasons tracked",
            "value": _format_number(seasons),
            "detail": f"{len(names)} team names across {len(leagues)} leagues.",
        },
        {
            "label": "All-time record",
            "value": _format_record(total_wins, total_losses),
            "detail": (
                f"{_format_percentage(total_wins / total_games)} win pct"
                if total_games
                else "No win-loss record recorded."
            ),
        },
        {
            "label": "Titles",
            "value": _format_number(sum(1 for season in history if season.get("world_series_winner"))),
            "detail": (
                f"{sum(1 for season in history if season.get('league_winner'))} league titles · "
                f"{sum(1 for season in history if season.get('division_winner'))} division crowns"
            ),
        },
        {
            "label": "Wild cards",
            "value": _format_number(sum(1 for season in history if season.get("wild_card_winner"))),
            "detail": "Seasons flagged as wild-card entries.",
        },
        {
            "label": "Home parks",
            "value": _format_number(len(parks)),
            "detail": "Distinct parks captured in the dataset.",
        },
        {
            "label": "Status",
            "value": "Active" if catalog_entry.get("active") else "Historical",
            "detail": f"Franchise code: {catalog_entry['franchise_id']}",
        },
    ]
    return profile


def _build_team_cards(franchise_catalog, selected_franchise):
    cards = []
    for entry in franchise_catalog:
        logo_id = _team_logo_id(
            entry.get("latest_team_id_br"),
            entry.get("latest_team_id"),
            entry.get("franchise_id"),
        )
        latest_wins = entry.get("latest_wins")
        latest_losses = entry.get("latest_losses")
        has_record = latest_wins is not None and latest_losses is not None
        cards.append(
            {
                "franchise_id": entry["franchise_id"],
                "name": entry["name"],
                "team_name": entry.get("latest_team_name") or entry["name"],
                "logo_id": logo_id,
                "active": entry.get("active"),
                "selected": entry["franchise_id"] == selected_franchise,
                "season_count_display": _format_number(entry.get("season_count")),
                "span_display": f"{entry.get('first_year')} - {entry.get('last_year')}",
                "latest_year_display": _format_number(entry.get("latest_year")),
                "league_name": _league_display(entry.get("latest_league_code")),
                "park": entry.get("latest_park") or "Park not recorded",
                "record_display": _format_record(latest_wins, latest_losses) if has_record else "Record N/A",
                "status_label": "Active franchise" if entry.get("active") else "Historical franchise",
                "badges": _catalog_badges(entry),
            }
        )
    return cards


def _build_team_showcase_facts(team, catalog_entry):
    return [
        {"label": "Franchise", "value": catalog_entry["name"]},
        {"label": "League", "value": _league_display(team.get("league_code"))},
        {"label": "Division", "value": _division_display(team.get("division_code"))},
        {"label": "Ballpark", "value": team.get("park") or "Unknown park"},
        {"label": "Attendance", "value": _format_number(team.get("attendance"))},
        {"label": "Games", "value": _format_number(team.get("games"))},
        {"label": "Home games", "value": _format_number(team.get("home_games"))},
        {"label": "Franchise span", "value": f"{catalog_entry['first_year']} - {catalog_entry['last_year']}"},
    ]


def _build_team_showcase_metrics(team):
    run_diff = team.get("run_diff")
    return [
        {
            "label": "Record",
            "value": _format_record(team.get("wins"), team.get("losses")),
            "detail": "Wins and losses in the selected season.",
        },
        {
            "label": "Win pct",
            "value": _format_percentage(team.get("win_pct")),
            "detail": "Winning percentage across all games.",
        },
        {
            "label": "Run diff",
            "value": f"{run_diff:+d}" if run_diff is not None else "N/A",
            "detail": "Runs scored minus runs allowed.",
        },
        {
            "label": "Team OPS",
            "value": _format_rate(team.get("ops"), 3, baseball_style=True),
            "detail": "On-base plus slugging for the club.",
        },
    ]


def _best_season(history, key_fn, reverse=True):
    def _normalize_sort_value(value):
        if isinstance(value, tuple):
            return tuple(_normalize_sort_value(item) for item in value)
        if value is None:
            return float("-inf")
        return value

    candidates = [season for season in history if key_fn(season) is not None]
    if not candidates:
        return None
    return sorted(candidates, key=lambda season: _normalize_sort_value(key_fn(season)), reverse=reverse)[0]


def _build_best_season_cards(history):
    cards = []

    best_record = _best_season(
        history,
        lambda season: (
            season.get("win_pct"),
            season.get("wins"),
            season.get("year"),
        )
        if season.get("win_pct") is not None
        else None,
    )
    if best_record:
        cards.append(
            {
                "title": "Best record",
                "icon": "bi-graph-up-arrow",
                "value": _format_percentage(best_record.get("win_pct")),
                "detail": f"{_format_record(best_record.get('wins'), best_record.get('losses'))} in {best_record.get('year')}",
            }
        )

    most_wins = _best_season(history, lambda season: (season.get("wins"), season.get("year")))
    if most_wins:
        cards.append(
            {
                "title": "Most wins",
                "icon": "bi-bar-chart-fill",
                "value": _format_number(most_wins.get("wins")),
                "detail": f"{most_wins.get('team_name')} · {most_wins.get('year')}",
            }
        )

    best_attendance = _best_season(history, lambda season: (season.get("attendance"), season.get("year")))
    if best_attendance and best_attendance.get("attendance"):
        cards.append(
            {
                "title": "Highest attendance",
                "icon": "bi-people-fill",
                "value": _format_number(best_attendance.get("attendance")),
                "detail": f"{best_attendance.get('park') or best_attendance.get('team_name')} · {best_attendance.get('year')}",
            }
        )

    best_offense = _best_season(history, lambda season: (season.get("runs"), season.get("year")))
    if best_offense:
        cards.append(
            {
                "title": "Most runs scored",
                "icon": "bi-lightning-charge-fill",
                "value": _format_number(best_offense.get("runs")),
                "detail": f"{best_offense.get('team_name')} · {best_offense.get('year')}",
            }
        )

    lowest_era = _best_season(
        history,
        lambda season: (-season.get("era"), season.get("year"))
        if season.get("era") is not None
        else None,
    )
    if lowest_era and lowest_era.get("era") is not None:
        cards.append(
            {
                "title": "Lowest ERA",
                "icon": "bi-shield-check",
                "value": _format_rate(lowest_era.get("era"), 2),
                "detail": f"{lowest_era.get('team_name')} · {lowest_era.get('year')}",
            }
        )

    return cards


def _build_stat_sections(team):
    offense_rows = [
        {"label": "Runs", "value": _format_number(team.get("runs")), "note": "Total runs scored."},
        {"label": "Hits", "value": _format_number(team.get("hits")), "note": "Combined team hits."},
        {"label": "Home runs", "value": _format_number(team.get("home_runs")), "note": "Long-ball output."},
        {"label": "Stolen bases", "value": _format_number(team.get("stolen_bases")), "note": "Successful steals."},
        {"label": "AVG", "value": _format_rate(team.get("avg"), 3, baseball_style=True), "note": "Team batting average."},
        {"label": "OBP", "value": _format_rate(team.get("obp"), 3, baseball_style=True), "note": "On-base percentage."},
        {"label": "SLG", "value": _format_rate(team.get("slg"), 3, baseball_style=True), "note": "Slugging percentage."},
        {"label": "OPS", "value": _format_rate(team.get("ops"), 3, baseball_style=True), "note": "On-base plus slugging."},
        {"label": "BB/K", "value": _format_rate(team.get("bb_k_ratio"), 2), "note": "Walk-to-strikeout ratio."},
    ]

    pitching_rows = [
        {"label": "ERA", "value": _format_rate(team.get("era"), 2), "note": "Team earned run average."},
        {"label": "Innings", "value": _format_innings(team.get("innings_outs")), "note": "Pitching workload in outs."},
        {"label": "Runs allowed", "value": _format_number(team.get("runs_allowed")), "note": "Runs conceded."},
        {"label": "Hits allowed", "value": _format_number(team.get("hits_allowed")), "note": "Hits surrendered."},
        {"label": "Walks allowed", "value": _format_number(team.get("walks_allowed")), "note": "Free passes issued."},
        {"label": "Strikeouts", "value": _format_number(team.get("strikeouts_pitching")), "note": "Pitching strikeouts."},
        {"label": "Saves", "value": _format_number(team.get("saves")), "note": "Team saves."},
        {"label": "Shutouts", "value": _format_number(team.get("shutouts")), "note": "Shutout wins."},
        {"label": "Complete games", "value": _format_number(team.get("complete_games")), "note": "Starts finished by one pitcher."},
    ]

    environment_rows = [
        {"label": "Park", "value": team.get("park") or "N/A", "note": "Primary home park for the season."},
        {"label": "Attendance", "value": _format_number(team.get("attendance")), "note": "Total recorded attendance."},
        {
            "label": "Avg home crowd",
            "value": _format_number(round(team["attendance_per_game"])) if team.get("attendance_per_game") else "N/A",
            "note": "Attendance divided by home games.",
        },
        {"label": "Fielding %", "value": _format_rate(team.get("fielding_pct"), 3, baseball_style=True), "note": "Team fielding percentage."},
        {"label": "Errors", "value": _format_number(team.get("errors")), "note": "Fielding errors committed."},
        {"label": "Double plays", "value": _format_number(team.get("double_plays")), "note": "Double plays turned."},
        {"label": "BPF", "value": _format_number(team.get("bpf")), "note": "Batting park factor."},
        {"label": "PPF", "value": _format_number(team.get("ppf")), "note": "Pitching park factor."},
    ]

    return [
        {"id": "offense", "title": "Offense", "icon": "bi-lightning-charge-fill", "rows": offense_rows},
        {"id": "pitching", "title": "Pitching", "icon": "bi-shield-fill", "rows": pitching_rows},
        {"id": "environment", "title": "Environment", "icon": "bi-building", "rows": environment_rows},
    ]


def _build_season_context_cards(team, postseason_rows):
    division_text = _division_display(team.get("division_code"))
    rank = team.get("rank")
    ranking_text = f"Ranked {rank} in the {division_text}" if rank else "Rank unavailable"
    park_detail = (
        f"{_format_number(round(team['attendance_per_game']))} per home game"
        if team.get("attendance_per_game")
        else "Attendance per game unavailable"
    )

    return [
        {
            "title": "Competition",
            "value": f"{_league_display(team.get('league_code'))} · {division_text}",
            "detail": ranking_text,
        },
        {
            "title": "Record",
            "value": _format_record(team.get("wins"), team.get("losses")),
            "detail": (
                f"{_format_percentage(team.get('win_pct'))} win pct · "
                f"{team.get('run_diff', 0):+d} run differential"
            ),
        },
        {
            "title": "Ballpark",
            "value": team.get("park") or "Unknown park",
            "detail": park_detail,
        },
        {
            "title": "Postseason",
            "value": _season_outcome(team, postseason_rows),
            "detail": (
                ", ".join(badge["label"] for badge in team.get("badges", []))
                if team.get("badges")
                else "No flags or series entries for this season."
            ),
        },
    ]


def _top_player(rows, key, reverse=True, minimum_key=None, minimum_value=0):
    candidates = []
    for row in rows:
        value = row.get(key)
        if value in (None, "", "N/A"):
            continue
        if minimum_key and row.get(minimum_key, 0) < minimum_value:
            continue
        candidates.append(row)

    if not candidates:
        return None

    return sorted(
        candidates,
        key=lambda row: (row.get(key), row.get(minimum_key, 0), row.get("name", "")),
        reverse=reverse,
    )[0]


def _build_leader_cards(hitters, pitchers):
    cards = []

    leader_specs = [
        ("Home run leader", hitters, "home_runs", "bi-stars", lambda row: _format_number(row.get("home_runs"))),
        ("RBI leader", hitters, "rbi", "bi-bullseye", lambda row: _format_number(row.get("rbi"))),
        ("AVG leader", hitters, "avg", "bi-dot", lambda row: _format_rate(row.get("avg"), 3, baseball_style=True), "at_bats", 100),
        ("OPS leader", hitters, "ops", "bi-speedometer2", lambda row: _format_rate(row.get("ops"), 3, baseball_style=True), "plate_appearances", 120),
        ("Strikeout leader", pitchers, "strikeouts", "bi-shield-fill", lambda row: _format_number(row.get("strikeouts"))),
        ("ERA leader", pitchers, "era", "bi-shield-check", lambda row: _format_rate(row.get("era"), 2), "innings_outs", 162, False),
        ("Saves leader", pitchers, "saves", "bi-lock-fill", lambda row: _format_number(row.get("saves"))),
    ]

    for spec in leader_specs:
        title, rows, key, icon, formatter = spec[:5]
        minimum_key = spec[5] if len(spec) > 5 else None
        minimum_value = spec[6] if len(spec) > 6 else 0
        reverse = spec[7] if len(spec) > 7 else True
        leader = _top_player(rows, key, reverse=reverse, minimum_key=minimum_key, minimum_value=minimum_value)
        if not leader:
            continue
        cards.append(
            {
                "title": title,
                "icon": icon,
                "value": formatter(leader),
                "detail": leader["name"],
                "player_id": leader["player_id"],
            }
        )

    return cards


def _prepare_hitter_table(hitters):
    rows = sorted(
        hitters,
        key=lambda row: (row.get("plate_appearances", 0), row.get("home_runs", 0), row.get("hits", 0)),
        reverse=True,
    )[:10]
    for row in rows:
        row["avg_display"] = _format_rate(row.get("avg"), 3, baseball_style=True)
        row["ops_display"] = _format_rate(row.get("ops"), 3, baseball_style=True)
        row["hr_display"] = _format_number(row.get("home_runs"))
        row["rbi_display"] = _format_number(row.get("rbi"))
        row["sb_display"] = _format_number(row.get("stolen_bases"))
    return rows


def _prepare_pitcher_table(pitchers):
    rows = sorted(
        pitchers,
        key=lambda row: (row.get("innings_outs", 0), row.get("strikeouts", 0), row.get("wins", 0)),
        reverse=True,
    )[:10]
    for row in rows:
        row["ip_display"] = _format_innings(row.get("innings_outs"))
        row["era_display"] = _format_rate(row.get("era"), 2)
        row["record_display"] = _format_record(row.get("wins"), row.get("losses"))
        row["so_display"] = _format_number(row.get("strikeouts"))
        row["sv_display"] = _format_number(row.get("saves"))
    return rows


def _group_awards(awards):
    grouped = {}
    for award in awards:
        grouped.setdefault(award["award_name"], []).append(award)

    rows = []
    for award_name, items in grouped.items():
        rows.append(
            {
                "award_name": award_name,
                "players": ", ".join(sorted(item["name"] for item in items)),
                "count": len(items),
            }
        )

    return sorted(rows, key=lambda row: (row["award_name"], row["players"]))

def _build_team_detail_context(requested_franchise, requested_year=""):
    franchise_catalog = get_team_franchise_catalog()
    catalog_map = {entry["franchise_id"]: entry for entry in franchise_catalog}
    catalog_entry = catalog_map.get(requested_franchise)
    team_history = get_team_history(requested_franchise) if catalog_entry else []
    season_options = [
        {
            "year": season["year"],
            "team_name": season["team_name"],
            "label": f"{season['year']} · {season['team_name']}",
        }
        for season in team_history
    ]

    selected_team = None
    if team_history:
        selected_team = next(
            (season for season in team_history if str(season["year"]) == requested_year),
            team_history[0],
        )

    postseason_history = []
    batting_roster = []
    pitching_roster = []
    managers = []
    all_stars = []
    awards = []

    if selected_team:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                "postseason": executor.submit(get_team_postseason_history, requested_franchise),
                "batting": executor.submit(get_team_batting_roster, selected_team["team_id"], selected_team["year"]),
                "pitching": executor.submit(get_team_pitching_roster, selected_team["team_id"], selected_team["year"]),
                "managers": executor.submit(get_team_managers, selected_team["team_id"], selected_team["year"]),
                "all_stars": executor.submit(get_team_all_stars, selected_team["team_id"], selected_team["year"]),
                "awards": executor.submit(get_team_awards, selected_team["team_id"], selected_team["year"]),
            }
            postseason_history = futures["postseason"].result()
            batting_roster = futures["batting"].result()
            pitching_roster = futures["pitching"].result()
            managers = futures["managers"].result()
            all_stars = futures["all_stars"].result()
            awards = futures["awards"].result()

        selected_team = {
            **selected_team,
            "franchise_id": requested_franchise,
            "franchise_name": catalog_entry["name"],
            "franchise_active": catalog_entry["active"],
            "league_name": _league_display(selected_team.get("league_code")),
            "division_name": _division_display(selected_team.get("division_code")),
            "logo_id": _team_logo_id(
                selected_team.get("team_id_br"),
                selected_team.get("team_id"),
                requested_franchise,
            ),
            "record_display": _format_record(selected_team.get("wins"), selected_team.get("losses")),
            "win_pct_display": _format_percentage(selected_team.get("win_pct")),
            "attendance_display": _format_number(selected_team.get("attendance")),
        }
        selected_team["badges"] = _season_badges(selected_team)

    selected_season_postseason = [
        row for row in postseason_history if selected_team and row.get("year") == selected_team["year"]
    ]

    franchise_profile = _build_franchise_profile(team_history, catalog_entry) if selected_team else []
    best_season_cards = _build_best_season_cards(team_history) if selected_team else []
    stat_sections = _build_stat_sections(selected_team) if selected_team else []
    season_context_cards = _build_season_context_cards(selected_team, selected_season_postseason) if selected_team else []
    leader_cards = _build_leader_cards(batting_roster, pitching_roster) if selected_team else []
    hitter_rows = _prepare_hitter_table(batting_roster) if selected_team else []
    pitcher_rows = _prepare_pitcher_table(pitching_roster) if selected_team else []
    grouped_awards = _group_awards(awards) if selected_team else []
    featured_history_rows = history_rows = []

    if selected_team:
        history_rows = []
        for season in team_history:
            history_rows.append(
                {
                    **season,
                    "league_name": _league_display(season.get("league_code")),
                    "division_name": _division_display(season.get("division_code")),
                    "record_display": _format_record(season.get("wins"), season.get("losses")),
                    "win_pct_display": _format_percentage(season.get("win_pct")),
                    "attendance_display": _format_number(season.get("attendance")),
                    "badges": _season_badges(season),
                    "is_selected": season["year"] == selected_team["year"],
                }
            )
        featured_history_rows = history_rows[:10]

    manager_rows = []
    for manager in managers:
        manager_rows.append(
            {
                **manager,
                "record_display": _format_record(manager.get("wins"), manager.get("losses")),
            }
        )

    team_tabs = []
    if selected_team:
        team_tabs.append({"id": "overview", "label": "Overview", "icon": "bi-grid-1x2-fill"})
        team_tabs.append({"id": "stats", "label": "Statistics", "icon": "bi-bar-chart-fill"})
        if hitter_rows or pitcher_rows or leader_cards or manager_rows or grouped_awards or all_stars:
            team_tabs.append({"id": "leaders", "label": "Squad & Staff", "icon": "bi-people-fill"})
        if history_rows:
            team_tabs.append({"id": "history", "label": "History", "icon": "bi-clock-history"})
        if postseason_history or selected_team.get("badges"):
            team_tabs.append({"id": "postseason", "label": "Postseason", "icon": "bi-trophy-fill"})

    selected_franchise_label = (
        f"{catalog_entry['name']} ({catalog_entry['franchise_id']})"
        if catalog_entry
        else ""
    )
    return {
        "page_title": (
            f"{selected_team['team_name']} {selected_team['year']} · Teams"
            if selected_team
            else "Teams"
        ),
        "selected_franchise": requested_franchise,
        "selected_franchise_label": selected_franchise_label,
        "season_options": season_options,
        "selected_team": selected_team,
        "team_showcase_facts": _build_team_showcase_facts(selected_team, catalog_entry) if selected_team else [],
        "team_showcase_metrics": _build_team_showcase_metrics(selected_team) if selected_team else [],
        "franchise_profile": franchise_profile,
        "season_context_cards": season_context_cards,
        "stat_sections": stat_sections,
        "leader_cards": leader_cards,
        "hitter_rows": hitter_rows,
        "pitcher_rows": pitcher_rows,
        "manager_rows": manager_rows,
        "all_stars": all_stars,
        "grouped_awards": grouped_awards,
        "history_rows": history_rows,
        "featured_history_rows": featured_history_rows,
        "best_season_cards": best_season_cards,
        "postseason_history": postseason_history,
        "selected_season_postseason": selected_season_postseason,
        "season_outcome": _season_outcome(selected_team, selected_season_postseason) if selected_team else "",
        "team_tabs": team_tabs,
    }


def _filter_team_directory(franchise_catalog, search_term, league_code, status, sort_code):
    filtered = []
    search_term_normalized = search_term.lower()

    for entry in franchise_catalog:
        if search_term_normalized:
            haystack = " ".join(
                str(value or "")
                for value in (
                    entry.get("name"),
                    entry.get("franchise_id"),
                    entry.get("latest_team_name"),
                    entry.get("latest_park"),
                )
            ).lower()
            if search_term_normalized not in haystack:
                continue

        if league_code and entry.get("latest_league_code") != league_code:
            continue

        if status == "active" and not entry.get("active"):
            continue
        if status == "historical" and entry.get("active"):
            continue

        filtered.append(entry)

    def _sort_key(entry):
        if sort_code == "latest_year_desc":
            return (entry.get("latest_year") or 0, entry.get("name", ""), entry.get("franchise_id", ""))
        if sort_code == "seasons_desc":
            return (entry.get("season_count") or 0, entry.get("name", ""), entry.get("franchise_id", ""))
        return (entry.get("name", ""), entry.get("franchise_id", ""))

    reverse = sort_code in {"latest_year_desc", "seasons_desc"}
    return sorted(filtered, key=_sort_key, reverse=reverse)


def _dedupe_team_directory(catalog):
    grouped = {}
    for entry in catalog:
        name = (entry.get("name") or "").strip()
        if not name:
            name = entry.get("franchise_id", "")
        grouped.setdefault(name, []).append(entry)

    deduped = []
    for name, entries in grouped.items():
        best = sorted(
            entries,
            key=lambda entry: (
                1 if entry.get("active") else 0,
                entry.get("latest_year") or 0,
                entry.get("season_count") or 0,
                entry.get("franchise_id", ""),
            ),
            reverse=True,
        )[0].copy()
        best["merged_count"] = len(entries)
        if len(entries) > 1:
            best["merged_franchise_ids"] = [entry.get("franchise_id", "") for entry in entries]
        deduped.append(best)

    return deduped

ROUND_LABELS = {
    "WS": "World Series",
    "ALCS": "American League Championship Series",
    "NLCS": "National League Championship Series",
    "ALDS1": "American League Division Series 1",
    "ALDS2": "American League Division Series 2",
    "NLDS1": "National League Division Series 1",
    "NLDS2": "National League Division Series 2",
    "ALWC": "American League Wild Card",
    "NLWC": "National League Wild Card",
    "AEDIV": "American League East Division Series",
    "AWDIV": "American League West Division Series",
    "NEDIV": "National League East Division Series",
    "NWDIV": "National League West Division Series",
}

LEAGUE_IMAGE_ASSETS = {
    "AL": "AL.png",
    "NL": "NL.png",
    "AA": "AA.png",
    "NA": "NLA.png",
    "PL": "PL.png",
    "FL": "FLL.png",
    "UA": "UA.png",
}


def teams_view(request):
    requested_franchise = str(
        request.GET.get("franchise") or request.GET.get("team") or ""
    ).strip().upper()
    requested_year = str(request.GET.get("year", "")).strip()

    if requested_franchise:
        detail_url = reverse("team_detail", kwargs={"franchise_id": requested_franchise})
        if requested_year:
            return redirect(f"{detail_url}?year={requested_year}")
        return redirect(detail_url)

    franchise_catalog = get_team_franchise_catalog()
    search_term = request.GET.get("q", "").strip()
    league_code = request.GET.get("league", "").strip().upper()
    status = request.GET.get("status", "all").strip().lower()
    sort_code = request.GET.get("sort", "name_asc").strip()

    valid_status = {"all", "active", "historical"}
    if status not in valid_status:
        status = "all"

    valid_sorts = {"name_asc", "latest_year_desc", "seasons_desc"}
    if sort_code not in valid_sorts:
        sort_code = "name_asc"

    valid_leagues = sorted(
        {entry.get("latest_league_code") for entry in franchise_catalog if entry.get("latest_league_code")}
    )
    if league_code and league_code not in valid_leagues:
        league_code = ""

    filtered_catalog = _filter_team_directory(franchise_catalog, search_term, league_code, status, sort_code)
    directory_catalog = _dedupe_team_directory(filtered_catalog)
    team_cards = _build_team_cards(directory_catalog, "")
    team_options = [
        {"player_id": entry["franchise_id"], "name": entry["name"]}
        for entry in _dedupe_team_directory(franchise_catalog)
    ]
    active_filters = []
    if search_term:
        active_filters.append({"label": "Query", "value": search_term})
    if league_code:
        active_filters.append({"label": "League", "value": _league_display(league_code)})
    if status == "active":
        active_filters.append({"label": "Status", "value": "Active"})
    elif status == "historical":
        active_filters.append({"label": "Status", "value": "Historical"})

    context = {
        "page_title": "Teams",
        "team_cards": team_cards,
        "team_options": team_options,
        "total_teams": len(directory_catalog),
        "search_term": search_term,
        "league_code": league_code,
        "status": status,
        "sort_code": sort_code,
        "league_options": [{"code": code, "name": _league_display(code)} for code in valid_leagues],
        "sort_options": [
            {"code": "name_asc", "name": "Name A-Z"},
            {"code": "latest_year_desc", "name": "Latest season"},
            {"code": "seasons_desc", "name": "Most seasons"},
        ],
        "active_filters": active_filters,
    }
    return render(request, "teams.html", context)


def team_detail_view(request, franchise_id):
    requested_franchise = str(franchise_id or "").strip().upper()
    detail_context = _build_team_detail_context(requested_franchise, str(request.GET.get("year", "")).strip())
    if not detail_context.get("selected_team"):
        raise Http404("Team not found")
    return render(request, "team_detail.html", detail_context)


def _merge_league_team_periods(teams):
    merged = {}
    for team in teams:
        name = (team.get("name") or "Unknown Team").strip()
        bucket = merged.setdefault(
            name,
            {
                "name": name,
                "franchises": set(),
                "park": team.get("park", ""),
                "seasons": 0,
                "first_year": team.get("first_year", 0),
                "last_year": team.get("last_year", 0),
            },
        )

        franchise = (team.get("franchise") or "").strip()
        if franchise:
            bucket["franchises"].add(franchise)

        bucket["seasons"] += team.get("seasons", 0) or 0

        first_year = team.get("first_year", 0) or 0
        last_year = team.get("last_year", 0) or 0
        if bucket["first_year"] == 0 or (first_year and first_year < bucket["first_year"]):
            bucket["first_year"] = first_year
        if last_year >= bucket["last_year"]:
            bucket["last_year"] = last_year
            bucket["park"] = team.get("park", "") or bucket.get("park", "")

    consolidated = []
    for team in merged.values():
        franchises = sorted(team.pop("franchises"))
        team["franchise"] = " / ".join(franchises)
        consolidated.append(team)

    return sorted(consolidated, key=lambda team: (team.get("name", ""), team.get("first_year", 0)))


def _build_league_metrics(league, teams, series_results):
    parks = sorted({team["park"] for team in teams if team.get("park")})
    sorted_teams = sorted(
        teams,
        key=lambda team: (-team.get("seasons", 0), team.get("first_year", 0), team.get("name", "")),
    )
    league_span = max((league.get("last_year", 0) or 0) - (league.get("first_year", 0) or 0) + 1, 1)
    top_teams = []
    for index, team in enumerate(sorted_teams[:6], start=1):
        active_years = max((team.get("last_year", 0) or 0) - (team.get("first_year", 0) or 0) + 1, 1)
        seasons = team.get("seasons", 0) or 0
        share = round((seasons / max(league.get("seasons", 1), 1)) * 100)
        if share >= 85:
            presence_label = "Foundational presence"
        elif share >= 50:
            presence_label = "Long-run contender"
        else:
            presence_label = "Historic chapter"

        enriched_team = {
            **team,
            "rank": index,
            "active_years": active_years,
            "league_share": share,
            "presence_label": presence_label,
            "recent_flag": "Still active at final league year" if team.get("last_year") == league.get("last_year") else "Historic run completed",
            "era_ratio": round((active_years / league_span) * 100),
        }
        top_teams.append(enriched_team)

    world_series = [series for series in series_results if series.get("round") == "WS"]
    playoffs = [series for series in series_results if series.get("round") != "WS"]
    round_breakdown = []
    seen_rounds = {}
    for series in playoffs:
        round_code = series.get("round") or "Unknown"
        bucket = seen_rounds.setdefault(
            round_code,
            {
                "round": round_code,
                "round_label": ROUND_LABELS.get(round_code, round_code),
                "series_count": 0,
                "first_year": None,
                "last_year": None,
                "total_games": 0,
                "internal_series": 0,
                "cross_league_series": 0,
                "latest_winner": "",
                "latest_loser": "",
            },
        )
        bucket["series_count"] += 1
        year = series.get("year")
        if year is not None:
            if bucket["first_year"] is None or year < bucket["first_year"]:
                bucket["first_year"] = year
            if bucket["last_year"] is None or year > bucket["last_year"]:
                bucket["last_year"] = year
                bucket["latest_winner"] = series.get("winner_team_name", "")
                bucket["latest_loser"] = series.get("loser_team_name", "")
        bucket["total_games"] += (series.get("wins") or 0) + (series.get("losses") or 0) + (series.get("ties") or 0)
        if series.get("winner_league") == league["code"] and series.get("loser_league") == league["code"]:
            bucket["internal_series"] += 1
        else:
            bucket["cross_league_series"] += 1

    round_breakdown = sorted(
        seen_rounds.values(),
        key=lambda item: (-item["series_count"], item["round"]),
    )

    recent_series = []
    for series in series_results[:8]:
        wins = series.get("wins") or 0
        losses = series.get("losses") or 0
        ties = series.get("ties") or 0
        scoreline = f"{wins}-{losses}"
        if ties:
            scoreline = f"{scoreline}-{ties}"
        recent_series.append(
            {
                **series,
                "round_label": ROUND_LABELS.get(series.get("round"), series.get("round") or "Unknown round"),
                "scoreline": scoreline,
                "winner_result": "League winner" if series.get("winner_league") == league["code"] else "Opponent winner",
            }
        )

    return {
        "park_count": len(parks),
        "parks": parks,
        "featured_teams": top_teams,
        "world_series_titles": sum(1 for series in world_series if series.get("winner_league") == league["code"]),
        "world_series_runner_up": sum(1 for series in world_series if series.get("loser_league") == league["code"]),
        "playoff_titles": sum(1 for series in playoffs if series.get("winner_league") == league["code"]),
        "playoff_runner_up": sum(1 for series in playoffs if series.get("loser_league") == league["code"]),
        "round_breakdown": round_breakdown,
        "recent_series": recent_series,
    }


def league_detail_view(request, league_code):
    league = get_league_detail(league_code)
    if not league:
        raise Http404("League not found")
    league["image_asset"] = LEAGUE_IMAGE_ASSETS.get(league["code"], "")
    teams_raw = get_teams_by_league(league_code)
    teams = _merge_league_team_periods(teams_raw)
    registry_mode = request.GET.get("registry", "clubs").strip().lower()
    if registry_mode not in {"clubs", "periods"}:
        registry_mode = "clubs"
    registry_search = request.GET.get("team", "").strip()
    registry_franchise = request.GET.get("franchise", "").strip().upper()
    registry_franchises = sorted({(team.get("franchise") or "").strip() for team in teams_raw if (team.get("franchise") or "").strip()})

    if registry_mode == "clubs":
        registry_teams = teams
    else:
        registry_teams = teams_raw
        if registry_search:
            search_term = registry_search.lower()
            registry_teams = [team for team in registry_teams if search_term in (team.get("name") or "").lower()]
        if registry_franchise:
            registry_teams = [team for team in registry_teams if (team.get("franchise") or "").strip().upper() == registry_franchise]

    all_series = get_league_series_results(league_code)
    world_series = [s for s in all_series if s["round"] == "WS"]
    playoffs = [s for s in all_series if s["round"] != "WS"]
    metrics = _build_league_metrics(league, teams, all_series)

    context = {
        "league": league,
        "teams": teams,
        "teams_raw": teams_raw,
        "registry_mode": registry_mode,
        "registry_teams": registry_teams,
        "registry_club_count": len(teams),
        "registry_period_count": len(teams_raw),
        "registry_search": registry_search,
        "registry_franchise": registry_franchise,
        "registry_franchises": registry_franchises,
        "world_series": world_series,
        "playoffs": playoffs,
        "series_results": all_series,
        **metrics,
    }
    return render(request, "league_detail.html", context)

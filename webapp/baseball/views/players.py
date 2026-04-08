from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from urllib.parse import urlencode

from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ..player_media import attach_player_media, enrich_players_with_media, fetch_player_photo_asset
from ..sparql import (
    get_player_filter_options,
    get_player_allstar_history,
    get_player_award_history,
    get_player_batting_seasons,
    get_player_batting_summary,
    get_players_catalog,
    get_players_catalog_count,
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


def _format_decimal(value, digits=3):
    if value is None:
        return "N/A"
    text = f"{float(value):.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _format_person_name_parts(name):
    name = str(name or "").strip()
    if not name:
        return {"first_name": "Unknown", "last_name": "Player", "full_name": "Unknown Player"}

    parts = [part for part in name.split() if part]
    if len(parts) == 1:
        return {"first_name": "", "last_name": parts[0], "full_name": parts[0]}

    return {
        "first_name": parts[0],
        "last_name": parts[-1],
        "full_name": name,
    }


def _location_display(*parts):
    values = []
    seen = set()
    for part in parts:
        text = str(part or "").strip()
        if not text or text.upper() == "N/A" or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return ", ".join(values) if values else "Unknown location"


def _date_display(year=None, month=None, day=None):
    months = {
        1: "Jan",
        2: "Feb",
        3: "Mar",
        4: "Apr",
        5: "May",
        6: "Jun",
        7: "Jul",
        8: "Aug",
        9: "Sep",
        10: "Oct",
        11: "Nov",
        12: "Dec",
    }

    try:
        year_value = int(str(year).strip())
    except (TypeError, ValueError, AttributeError):
        year_value = None

    try:
        month_value = int(str(month).strip())
    except (TypeError, ValueError, AttributeError):
        month_value = None

    try:
        day_value = int(str(day).strip())
    except (TypeError, ValueError, AttributeError):
        day_value = None

    if year_value and month_value in months and day_value:
        return f"{day_value} {months[month_value]} {year_value}"
    if year_value and month_value in months:
        return f"{months[month_value]} {year_value}"
    if year_value:
        return str(year_value)
    return "Unknown date"


def _summary_date_location(date_value, place_value):
    if date_value == "Unknown date" and place_value == "Unknown location":
        return "N/A"
    if place_value == "Unknown location":
        return date_value
    if date_value == "Unknown date":
        return place_value
    return f"{date_value} · {place_value}"


def _primary_place(city=None, state=None, country=None):
    for value in (city, state, country):
        text = str(value or "").strip()
        if text and text.upper() != "N/A":
            return text
    return "Unknown place"


def _build_player_card(player):
    initials = "".join(part[0] for part in player["name"].split()[:2]).upper() or "P"
    debut_year = _year_from_date(player.get("debut"))
    final_year = _year_from_date(player.get("final_game"))
    name_parts = _format_person_name_parts(player.get("name"))

    if debut_year and final_year:
        career_span = f"{debut_year} - {final_year}"
    elif debut_year:
        career_span = f"Since {debut_year}"
    else:
        career_span = "Career data unavailable"

    return {
        **player,
        **name_parts,
        "initials": initials[:2],
        "birth_year_display": _format_text(player.get("birth_year"), "Unknown year"),
        "birth_country_display": _format_text(player.get("birth_country"), "Unknown country"),
        "height_display": _format_text(player.get("height")),
        "weight_display": _format_text(player.get("weight")),
        "bats_throws_display": f"{_format_text(player.get('bats'))} / {_format_text(player.get('throws'))}",
        "debut_display": _format_text(player.get("debut")),
        "final_game_display": _format_text(player.get("final_game")),
        "career_span_display": career_span,
        "birth_date_display": _date_display(
            player.get("birth_year"),
            player.get("birth_month"),
            player.get("birth_day"),
        ),
        "death_date_display": _date_display(
            player.get("death_year"),
            player.get("death_month"),
            player.get("death_day"),
        ),
        "birth_place_display": _location_display(
            player.get("birth_city"),
            player.get("birth_state"),
            player.get("birth_country"),
        ),
        "death_place_display": _location_display(
            player.get("death_city"),
            player.get("death_state"),
            player.get("death_country"),
        ),
        "has_death_data": any(
            player.get(key)
            for key in ("death_year", "death_month", "death_day", "death_city", "death_state", "death_country")
        ),
        "birth_summary_display": _summary_date_location(
            _date_display(
                player.get("birth_year"),
                player.get("birth_month"),
                player.get("birth_day"),
            ),
            _location_display(
                player.get("birth_city"),
                player.get("birth_state"),
                player.get("birth_country"),
            ),
        ),
        "birth_primary_place": _primary_place(
            player.get("birth_city"),
            player.get("birth_state"),
            player.get("birth_country"),
        ),
        "death_summary_display": _summary_date_location(
            _date_display(
                player.get("death_year"),
                player.get("death_month"),
                player.get("death_day"),
            ),
            _location_display(
                player.get("death_city"),
                player.get("death_state"),
                player.get("death_country"),
            ),
        ),
        "death_primary_place": _primary_place(
            player.get("death_city"),
            player.get("death_state"),
            player.get("death_country"),
        ),
    }


def _attach_player_roster_context(player):
    history = get_player_team_history(player.get("player_id", ""))
    latest_entry = None
    for entry in reversed(history):
        if entry.get("team_name") or entry.get("franchise_name") or entry.get("league"):
            latest_entry = entry
            break

    latest_team = ""
    latest_franchise = ""
    latest_league = ""
    latest_season = None
    if latest_entry:
        latest_team = latest_entry.get("team_name", "")
        latest_franchise = latest_entry.get("franchise_name", "")
        latest_league = latest_entry.get("league", "")
        latest_season = latest_entry.get("year")

    return {
        **player,
        "latest_team_display": _format_text(latest_team or latest_franchise, "No team data"),
        "latest_franchise_display": _format_text(latest_franchise or latest_team, "No franchise data"),
        "latest_league_display": _format_text(latest_league, "League N/A"),
        "latest_season_display": _format_text(latest_season, "Season N/A"),
    }


def _enrich_players_with_roster_context(players, max_workers=8):
    if not players:
        return []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(_attach_player_roster_context, players))


def _latest_team_snapshot(profile):
    history = sorted(
        profile.get("team_history", []),
        key=lambda item: (item.get("year") or 0, item.get("team_name") or "", item.get("franchise_name") or ""),
        reverse=True,
    )
    for item in history:
        if item.get("team_name") or item.get("franchise_name") or item.get("league"):
            return {
                "team": _format_text(item.get("team_name") or item.get("franchise_name"), "No team data"),
                "franchise": _format_text(item.get("franchise_name") or item.get("team_name"), "No franchise data"),
                "league": _format_text(item.get("league"), "League N/A"),
                "year": _format_text(item.get("year"), "Season N/A"),
            }
    return {
        "team": "No team data",
        "franchise": "No franchise data",
        "league": "League N/A",
        "year": "Season N/A",
    }


def _build_player_detail_payload(profile):
    latest_snapshot = _latest_team_snapshot(profile)
    peak_salary_entry = profile.get("peak_salary_entry") or {}
    birth_date = _date_display(profile.get("birth_year"), profile.get("birth_month"), profile.get("birth_day"))
    birth_place = _location_display(profile.get("birth_city"), profile.get("birth_state"), profile.get("birth_country"))
    death_date = _date_display(profile.get("death_year"), profile.get("death_month"), profile.get("death_day"))
    death_place = _location_display(profile.get("death_city"), profile.get("death_state"), profile.get("death_country"))

    spotlight_stats = [
        {"label": "Documented seasons", "value": _format_number(profile.get("career_seasons", 0)), "detail": profile.get("career_span_years") and f"Span of {profile['career_span_years']} years" or "Season span unavailable"},
        {"label": "Teams represented", "value": _format_number(profile.get("team_count", 0)), "detail": latest_snapshot["team"]},
        {"label": "Awards logged", "value": _format_number(profile.get("award_count_total", 0)), "detail": profile.get("latest_award_year") and f"Latest in {profile['latest_award_year']}" or "No awards logged"},
        {"label": "All-Star apps", "value": _format_number(profile.get("allstar_count", 0)), "detail": profile.get("allstar_years") and _summarize_values(profile["allstar_years"], limit=4) or "No All-Star appearances"},
        {"label": "Peak salary", "value": _format_currency(profile.get("peak_salary")), "detail": peak_salary_entry.get("detail", "No salary data")},
        {"label": "Hall of Fame", "value": "Inducted" if profile["hall_of_fame"].get("inducted") else "Not inducted", "detail": profile["hall_of_fame"].get("inducted_year") and str(profile["hall_of_fame"]["inducted_year"]) or f"{profile['hall_of_fame'].get('vote_count', 0)} ballot entries"},
    ]

    identity_chips = [
        latest_snapshot["team"],
        latest_snapshot["league"],
        _format_text(profile.get("birth_country"), "Unknown country"),
    ]
    if profile["hall_of_fame"].get("inducted"):
        identity_chips.append("Hall of Fame")

    bio_items = [
        {"label": "Player ID", "value": _format_text(profile.get("player_id"))},
        {"label": "Born", "value": _summary_date_location(birth_date, birth_place)},
        {"label": "Died", "value": _summary_date_location(death_date, death_place) if death_date != "Unknown date" or death_place != "Unknown location" else "Still active / no death data"},
        {"label": "Bats / throws", "value": f"{_format_text(profile.get('bats'))} / {_format_text(profile.get('throws'))}"},
        {"label": "Height / weight", "value": f"{_format_text(profile.get('height'))} / {_format_text(profile.get('weight'))}"},
        {"label": "Debut", "value": _format_text(profile.get("debut"))},
        {"label": "Final game", "value": _format_text(profile.get("final_game"))},
        {"label": "First season", "value": _format_text(profile.get("first_season"))},
        {"label": "Last season", "value": _format_text(profile.get("last_season"))},
        {"label": "Latest team", "value": latest_snapshot["team"]},
        {"label": "Franchises", "value": _format_number(profile.get("franchise_count", 0))},
        {"label": "Leagues", "value": _format_number(profile.get("league_count", 0))},
    ]

    best_season_highlights = [
        item for item in (
            profile.get("best_hr_entry"),
            profile.get("best_rbi_entry"),
            profile.get("best_era_entry"),
            profile.get("peak_salary_entry"),
        )
        if item
    ]

    batting_overview = [
        {"label": "Games", "value": _format_number(profile["batting_summary"].get("games"))},
        {"label": "At-bats", "value": _format_number(profile["batting_summary"].get("at_bats"))},
        {"label": "Hits", "value": _format_number(profile["batting_summary"].get("hits"))},
        {"label": "Home runs", "value": _format_number(profile["batting_summary"].get("home_runs"))},
        {"label": "RBI", "value": _format_number(profile["batting_summary"].get("rbi"))},
        {"label": "AVG", "value": _format_decimal(profile["batting_summary"].get("avg"))},
        {"label": "OBP", "value": _format_decimal(profile["batting_summary"].get("obp"))},
        {"label": "SLG", "value": _format_decimal(profile["batting_summary"].get("slg"))},
        {"label": "OPS", "value": _format_decimal(profile["batting_summary"].get("ops"))},
        {"label": "HR / season", "value": _format_decimal(profile["batting_summary"].get("hr_per_season"))},
    ]

    pitching_overview = [
        {"label": "Pitching seasons", "value": _format_number(profile["pitching_summary"].get("seasons"))},
        {"label": "Wins", "value": _format_number(profile["pitching_summary"].get("wins"))},
        {"label": "Losses", "value": _format_number(profile["pitching_summary"].get("losses"))},
        {"label": "Strikeouts", "value": _format_number(profile["pitching_summary"].get("strikeouts"))},
        {"label": "Saves", "value": _format_number(profile["pitching_summary"].get("saves"))},
        {"label": "ERA", "value": _format_decimal(profile["pitching_summary"].get("era"), digits=2)},
        {"label": "Games started", "value": _format_number(profile["pitching_summary"].get("games_started"))},
        {"label": "Innings pitched", "value": _format_ip_outs(profile["pitching_summary"].get("innings_outs"))},
    ]

    affiliation_panels = [
        {"label": "Teams", "value": _format_number(profile.get("team_count", 0)), "detail": _summarize_values(profile.get("team_names", []), limit=5)},
        {"label": "Franchises", "value": _format_number(profile.get("franchise_count", 0)), "detail": _summarize_values(profile.get("franchise_names", []), limit=5)},
        {"label": "Leagues", "value": _format_number(profile.get("league_count", 0)), "detail": _summarize_values(profile.get("league_names", []), limit=5)},
        {"label": "Latest season", "value": latest_snapshot["year"], "detail": latest_snapshot["team"]},
    ]

    recognition_items = []
    for item in profile.get("recent_awards", []):
        recognition_items.append({"label": item["label"], "value": item["value"], "detail": item.get("detail", "")})
    if not recognition_items:
        for item in profile.get("allstar_items", []):
            recognition_items.append({"label": item["label"], "value": item["value"], "detail": ""})
    if profile["hall_of_fame"].get("inducted"):
        recognition_items.insert(0, {"label": "Hall of Fame", "value": "Inducted", "detail": str(profile["hall_of_fame"]["inducted_year"])})

    return {
        "latest_snapshot": latest_snapshot,
        "identity_chips": identity_chips,
        "spotlight_stats": spotlight_stats,
        "bio_items": bio_items,
        "best_season_highlights": best_season_highlights,
        "batting_overview": batting_overview,
        "pitching_overview": pitching_overview,
        "affiliation_panels": affiliation_panels,
        "recognition_items": recognition_items,
    }


def _build_player_graph_payload(player):
    graph_data = deepcopy(get_player_graph_data(player.get("player_id", "")))
    photo_url = ""
    if player.get("photo_url") or player.get("photo_fallback_url"):
        photo_url = reverse("player_graph_photo", kwargs={"player_id": player.get("player_id", "")})

    if photo_url:
        for node in graph_data.get("nodes", []):
            node_data = node.get("data", {})
            if node_data.get("type") == "player":
                node_data["photoUrl"] = photo_url
                break

    return {
        "graph_nodes": graph_data.get("nodes", []),
        "graph_edges": graph_data.get("edges", []),
        "has_player_graph": bool(graph_data.get("nodes")),
    }


def player_graph_photo_view(request, player_id):
    summary = get_player_summary(player_id)
    if not summary:
        raise Http404("Player not found")

    player = attach_player_media(summary)
    photo_url = player.get("photo_url") or player.get("photo_fallback_url") or ""
    if not photo_url:
        raise Http404("Photo not found")

    image_bytes, content_type = fetch_player_photo_asset(photo_url)
    if not image_bytes:
        raise Http404("Photo not available")

    response = HttpResponse(image_bytes, content_type=content_type or "image/jpeg")
    response["Cache-Control"] = "public, max-age=86400"
    return response


def _build_player_list_querystring(params, **updates):
    query = {key: value for key, value in params.items() if value not in (None, "", False)}
    for key, value in updates.items():
        if value in (None, "", False):
            query.pop(key, None)
        else:
            query[key] = value
    return urlencode(query)


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
    letters = _alphabet()
    filter_options = get_player_filter_options()
    selected_letter = request.GET.get("letter", "").strip().upper()
    search_term = request.GET.get("q", "").strip()
    birth_country = request.GET.get("birth_country", "").strip()
    bats = request.GET.get("bats", "").strip().upper()
    throws = request.GET.get("throws", "").strip().upper()
    debut_decade = request.GET.get("debut_decade", "").strip()
    sort = request.GET.get("sort", "name_asc").strip()
    has_photo = request.GET.get("has_photo") in {"1", "true", "on"}

    try:
        page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        page = 1

    if selected_letter and selected_letter not in letters:
        selected_letter = ""
    if birth_country and birth_country not in filter_options["countries"]:
        birth_country = ""
    if bats not in {"", "L", "R", "B"}:
        bats = ""
    if throws not in {"", "L", "R"}:
        throws = ""
    valid_decades = {str(decade) for decade in filter_options["debut_decades"]}
    if debut_decade and debut_decade not in valid_decades:
        debut_decade = ""
    valid_sorts = {item["code"] for item in filter_options["sorts"]}
    if sort not in valid_sorts:
        sort = "name_asc"

    page_size = 24
    total_players = get_players_catalog_count(
        selected_letter,
        search_term,
        birth_country,
        bats,
        throws,
        debut_decade,
        has_photo,
    )
    total_pages = max((total_players + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    offset = (page - 1) * page_size

    players = [
        _build_player_card(player)
        for player in get_players_catalog(
            selected_letter,
            search_term,
            birth_country,
            bats,
            throws,
            debut_decade,
            has_photo,
            sort,
            page_size,
            offset,
        )
    ]
    players = _enrich_players_with_roster_context(players)
    players = enrich_players_with_media(players)
    page_numbers = list(range(max(1, page - 2), min(total_pages, page + 2) + 1))
    base_params = {
        "q": search_term,
        "letter": selected_letter,
        "birth_country": birth_country,
        "bats": bats,
        "throws": throws,
        "debut_decade": debut_decade,
        "sort": sort,
        "has_photo": "1" if has_photo else "",
    }

    active_filters = []
    if search_term:
        active_filters.append({"label": "", "value": search_term, "soft": True})
    if selected_letter:
        active_filters.append({"label": "Initial", "value": selected_letter})
    if birth_country:
        active_filters.append({"label": "Country", "value": birth_country})
    if bats:
        bats_name = next((item["name"] for item in filter_options["bats"] if item["code"] == bats), bats)
        active_filters.append({"label": "Bats", "value": bats_name})
    if throws:
        throws_name = next((item["name"] for item in filter_options["throws"] if item["code"] == throws), throws)
        active_filters.append({"label": "Throws", "value": throws_name})
    if debut_decade:
        active_filters.append({"label": "Debut era", "value": f"{debut_decade}s"})
    if has_photo:
        active_filters.append({"label": "Media", "value": "Photo available"})

    context = {
        "letters": letters,
        "filter_options": filter_options,
        "selected_letter": selected_letter,
        "search_term": search_term,
        "birth_country": birth_country,
        "bats": bats,
        "throws": throws,
        "debut_decade": debut_decade,
        "sort": sort,
        "has_photo": has_photo,
        "active_filters": active_filters,
        "players": players,
        "total_players": total_players,
        "page": page,
        "total_pages": total_pages,
        "page_numbers": page_numbers,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1,
        "next_page": page + 1,
        "pagination_query": _build_player_list_querystring(base_params),
        "page_query_builder": base_params,
        "comparator_url": reverse("compare_players"),
        "analytics_url": reverse("analytics"),
    }
    return render(request, "players.html", context)


def player_detail_view(request, player_id):
    player = _build_compare_profile(player_id)
    if not player:
        raise Http404("Player not found")
    player = attach_player_media(player)
    detail_payload = _build_player_detail_payload(player)
    graph_payload = _build_player_graph_payload(player)

    context = {
        "player": player,
        **detail_payload,
        **graph_payload,
        "recent_salary_history": player["salary_history"][:10],
        "recent_team_history": sorted(
            player["team_history"],
            key=lambda item: (item.get("year") or 0, item.get("team_name") or ""),
            reverse=True,
        )[:12],
        "recent_batting_seasons": sorted(
            player["batting_seasons_detail"],
            key=lambda item: item.get("year") or 0,
            reverse=True,
        )[:8],
        "recent_pitching_seasons": sorted(
            player["pitching_seasons_detail"],
            key=lambda item: item.get("year") or 0,
            reverse=True,
        )[:8],
    }
    return render(request, "player_detail.html", context)


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
    player_term = request.GET.get("player", "").strip()
    if player_term:
        target = reverse("player_detail", kwargs={"player_id": player_term})
        return redirect(f"{target}#relationship-graph")
    return redirect(reverse("players"))

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import lru_cache
from urllib.parse import urlencode

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from ..compare_selection import (
    clear_compare_selection,
    get_compare_selection,
    toggle_compare_selection,
)
from ..edit_service import build_player_edit_state
from ..player_media import (
    attach_player_media,
    enrich_players_with_media,
    fetch_player_photo_asset,
    get_catalog_photo_count,
    player_has_catalog_photo,
)
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
from ..sparql_queries.base import run_describe

BB_PLAYER_URI = "http://baseball.ws.pt/player/{}"


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


def _format_percentage(value, digits=1):
    if value in (None, "", "N/A"):
        return "N/A"
    return f"{float(value) * 100:.{digits}f}%"


def _format_signed_number(value):
    if value in (None, "", "N/A"):
        return "N/A"
    return f"{int(value):+d}"


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
        {"label": "Birth country", "value": _format_text(profile.get("birth_country")), "field_key": "birth_country"},
        {"label": "Birth state", "value": _format_text(profile.get("birth_state")), "field_key": "birth_state"},
        {"label": "Birth city", "value": _format_text(profile.get("birth_city")), "field_key": "birth_city"},
        {"label": "Died", "value": _summary_date_location(death_date, death_place) if death_date != "Unknown date" or death_place != "Unknown location" else "Still active / no death data"},
        {"label": "Bats", "value": _format_text(profile.get("bats")), "field_key": "bats"},
        {"label": "Throws", "value": _format_text(profile.get("throws")), "field_key": "throws"},
        {"label": "Height / weight", "value": f"{_format_text(profile.get('height'))} / {_format_text(profile.get('weight'))}"},
        {"label": "Debut", "value": _format_text(profile.get("debut")), "field_key": "debut"},
        {"label": "Final game", "value": _format_text(profile.get("final_game")), "field_key": "final_game"},
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
    direct_photo_url = (
        player.get("card_photo_url")
        or player.get("photo_url")
        or ""
    )
    fallback_photo_url = (
        player.get("card_photo_fallback_url")
        or player.get("photo_fallback_url")
        or ""
    )
    proxy_photo_url = ""
    if player.get("photo_url") or player.get("photo_fallback_url"):
        proxy_photo_url = reverse("player_graph_photo", kwargs={"player_id": player.get("player_id", "")})

    for node in graph_data.get("nodes", []):
        node_data = node.get("data", {})
        node_type = node_data.get("type")

        if node_type == "player":
            if proxy_photo_url:
                node_data["photoProxyUrl"] = proxy_photo_url
            if direct_photo_url:
                node_data["photoUrl"] = direct_photo_url
            if fallback_photo_url:
                node_data["photoFallbackUrl"] = fallback_photo_url
            continue

        if node_type == "teammate":
            teammate_id = node_data.get("playerID")
            if teammate_id:
                node_data["photoProxyUrl"] = reverse("player_graph_photo", kwargs={"player_id": teammate_id})

    return {
        "graph_nodes": graph_data.get("nodes", []),
        "graph_edges": graph_data.get("edges", []),
        "has_player_graph": bool(graph_data.get("nodes")),
    }


def player_graph_photo_view(request, player_id):
    placeholder_svg = """
    <svg xmlns="http://www.w3.org/2000/svg" width="220" height="220" viewBox="0 0 220 220">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#dbe7ff"/>
          <stop offset="100%" stop-color="#8fb0e8"/>
        </linearGradient>
      </defs>
      <rect width="220" height="220" rx="110" fill="url(#g)"/>
      <circle cx="110" cy="82" r="42" fill="#f8fbff"/>
      <path d="M52 188c10-34 34-54 58-54s48 20 58 54" fill="#f8fbff"/>
    </svg>
    """.strip()

    summary = get_player_summary(player_id)
    if not summary:
        return HttpResponse(placeholder_svg, content_type="image/svg+xml")

    player = attach_player_media(summary)
    photo_candidates = [
        str(player.get("photo_url") or "").strip(),
        str(player.get("photo_fallback_url") or "").strip(),
    ]
    photo_candidates = [url for url in photo_candidates if url]
    if not photo_candidates:
        return HttpResponse(placeholder_svg, content_type="image/svg+xml")

    image_bytes = None
    content_type = None
    for photo_url in photo_candidates:
        image_bytes, content_type = fetch_player_photo_asset(photo_url)
        if image_bytes:
            break

    if not image_bytes:
        return HttpResponse(placeholder_svg, content_type="image/svg+xml")

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


def _filter_catalog_players_with_photo(players):
    filtered = []
    for player in players:
        bbref_id = player.get("bbref_id", "")
        if not player_has_catalog_photo(bbref_id):
            continue
        filtered.append(player)
    return filtered


@lru_cache(maxsize=128)
def _count_catalog_players_with_photo(letter="", search_term="", birth_country="", bats="", throws="", debut_decade=""):
    if not any((letter, search_term, birth_country, bats, throws, debut_decade)):
        return get_catalog_photo_count()

    total = 0
    batch_offset = 0
    batch_size = 500

    while True:
        chunk = get_players_catalog(
            letter,
            search_term,
            birth_country,
            bats,
            throws,
            debut_decade,
            False,
            "name_asc",
            batch_size,
            batch_offset,
        )
        if not chunk:
            break

        total += len(_filter_catalog_players_with_photo(chunk))
        batch_offset += batch_size

        if len(chunk) < batch_size:
            break

    return total


def _get_catalog_players_page_with_photo(
    letter="",
    search_term="",
    birth_country="",
    bats="",
    throws="",
    debut_decade="",
    sort="name_asc",
    page_size=16,
    offset=0,
):
    target_end = offset + page_size
    batch_offset = 0
    batch_size = max(page_size * 4, 64)
    filtered_players = []

    while len(filtered_players) < target_end:
        chunk = get_players_catalog(
            letter,
            search_term,
            birth_country,
            bats,
            throws,
            debut_decade,
            False,
            sort,
            batch_size,
            batch_offset,
        )
        if not chunk:
            break

        filtered_players.extend(_filter_catalog_players_with_photo(chunk))
        batch_offset += batch_size

        if len(chunk) < batch_size:
            break

    return filtered_players[offset:target_end]


def _summarize_values(values, limit=4):
    if not values:
        return "No overlap yet"
    values = [str(value) for value in values if value]
    if not values:
        return "No overlap yet"
    if len(values) <= limit:
        return ", ".join(values)
    return f"{', '.join(values[:limit])} +{len(values) - limit} more"


def _build_player_active_filters(search_term, selected_letter, birth_country, bats, throws, debut_decade, has_photo, filter_options):
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
    return active_filters


def _build_players_catalog_context(
    request,
    *,
    selected_letter,
    search_term,
    birth_country,
    bats,
    throws,
    debut_decade,
    sort,
    has_photo,
    active_filters,
):
    page_size = 12
    try:
        requested_page = max(int(request.GET.get("page", "1")), 1)
    except ValueError:
        requested_page = 1

    requested_offset = (requested_page - 1) * page_size

    if has_photo:
        with ThreadPoolExecutor(max_workers=2) as executor:
            total_future = executor.submit(
                _count_catalog_players_with_photo,
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
            )
            players_future = executor.submit(
                _get_catalog_players_page_with_photo,
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
                sort,
                page_size,
                requested_offset,
            )
            total_players = total_future.result()
            raw_players = players_future.result()
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            total_future = executor.submit(
                get_players_catalog_count,
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
                False,
            )
            players_future = executor.submit(
                get_players_catalog,
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
                False,
                sort,
                page_size,
                requested_offset,
            )
            total_players = total_future.result()
            raw_players = players_future.result()

    total_pages = max((total_players + page_size - 1) // page_size, 1)
    page = min(requested_page, total_pages)

    if page != requested_page:
        offset = (page - 1) * page_size
        raw_players = (
            _get_catalog_players_page_with_photo(
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
                sort,
                page_size,
                offset,
            )
            if has_photo
            else get_players_catalog(
                selected_letter,
                search_term,
                birth_country,
                bats,
                throws,
                debut_decade,
                False,
                sort,
                page_size,
                offset,
            )
        )

    players = [_build_player_card(player) for player in raw_players]
    players = enrich_players_with_media(players)
    selected_players = _selected_compare_map(request, "player")
    for player in players:
        player["compare_selected"] = player["player_id"] in selected_players

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

    return {
        "players": players,
        "total_players": total_players,
        "active_filters": active_filters,
        "page": page,
        "total_pages": total_pages,
        "page_numbers": list(range(max(1, page - 2), min(total_pages, page + 2) + 1)),
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1,
        "next_page": page + 1,
        "pagination_query": _build_player_list_querystring(base_params),
    }


def _build_compare_row(
    label,
    player1_value,
    player2_value,
    *,
    display_formatter=_format_number,
    delta_formatter=None,
    better="higher",
    note="",
    side_1_label="Player 1",
    side_2_label="Player 2",
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
            winner_display = side_1_label if left else side_2_label
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
        winner_display = side_1_label
        delta_display = "Only player with data"
    elif left is None:
        winner_side = "player2"
        winner_display = side_2_label
        delta_display = "Only player with data"
    elif abs(left - right) < 1e-9:
        winner_side = "tie"
        winner_display = "Tie"
        delta_display = "Even"
    else:
        player1_wins = left < right if better == "lower" else left > right
        winner_side = "player1" if player1_wins else "player2"
        winner_display = side_1_label if player1_wins else side_2_label
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


def _selected_compare_map(request, item_type):
    selection = get_compare_selection(request)
    if selection["type"] != item_type:
        return {}
    return {
        item["id"]: item
        for item in selection["items"]
    }


def _build_team_compare_profile(franchise_id, year=""):
    from .teams import _build_team_detail_context

    detail_context = _build_team_detail_context(franchise_id, str(year or "").strip())
    selected_team = detail_context.get("selected_team")
    if not selected_team:
        return None

    history_rows = detail_context.get("history_rows", [])
    world_series_titles = sum(1 for row in history_rows if row.get("world_series_winner"))
    league_titles = sum(1 for row in history_rows if row.get("league_winner"))
    division_titles = sum(1 for row in history_rows if row.get("division_winner"))
    wild_cards = sum(1 for row in history_rows if row.get("wild_card_winner"))
    season_years = [row.get("year") for row in history_rows if row.get("year")]

    return {
        "franchise_id": franchise_id,
        "name": selected_team.get("team_name"),
        "team_name": selected_team.get("team_name"),
        "franchise_name": selected_team.get("franchise_name"),
        "league_name": selected_team.get("league_name"),
        "division_name": selected_team.get("division_name"),
        "logo_id": selected_team.get("logo_id"),
        "year": selected_team.get("year"),
        "record_display": selected_team.get("record_display"),
        "win_pct_display": selected_team.get("win_pct_display"),
        "attendance_display": selected_team.get("attendance_display"),
        "season_outcome": detail_context.get("season_outcome"),
        "history_rows": history_rows,
        "season_context_cards": detail_context.get("season_context_cards", []),
        "best_season_cards": detail_context.get("best_season_cards", []),
        "postseason_history": detail_context.get("postseason_history", []),
        "selected_season_postseason": detail_context.get("selected_season_postseason", []),
        "selected_team": selected_team,
        "card_stats": [
            {"label": "Season", "value": str(selected_team.get("year") or "N/A")},
            {"label": "League", "value": selected_team.get("league_name") or "N/A"},
            {"label": "Record", "value": selected_team.get("record_display") or "N/A"},
            {"label": "Win pct", "value": selected_team.get("win_pct_display") or "N/A"},
            {"label": "Park", "value": selected_team.get("park") or "N/A"},
            {"label": "Attendance", "value": selected_team.get("attendance_display") or "N/A"},
        ],
        "franchise_summary": {
            "seasons": len(history_rows),
            "first_year": min(season_years) if season_years else None,
            "last_year": max(season_years) if season_years else None,
            "world_series_titles": world_series_titles,
            "league_titles": league_titles,
            "division_titles": division_titles,
            "wild_cards": wild_cards,
        },
    }


def _build_team_compare_tabs(team1, team2):
    team_compare_kwargs = {"side_1_label": "Team 1", "side_2_label": "Team 2"}
    franchise_rows = [
        _build_compare_row("Seasons tracked", team1["franchise_summary"]["seasons"], team2["franchise_summary"]["seasons"], **team_compare_kwargs),
        _build_compare_row("First year", team1["franchise_summary"]["first_year"], team2["franchise_summary"]["first_year"], better="lower", **team_compare_kwargs),
        _build_compare_row("Last year", team1["franchise_summary"]["last_year"], team2["franchise_summary"]["last_year"], **team_compare_kwargs),
        _build_compare_row("World Series titles", team1["franchise_summary"]["world_series_titles"], team2["franchise_summary"]["world_series_titles"], **team_compare_kwargs),
        _build_compare_row("League titles", team1["franchise_summary"]["league_titles"], team2["franchise_summary"]["league_titles"], **team_compare_kwargs),
        _build_compare_row("Division titles", team1["franchise_summary"]["division_titles"], team2["franchise_summary"]["division_titles"], **team_compare_kwargs),
        _build_compare_row("Wild cards", team1["franchise_summary"]["wild_cards"], team2["franchise_summary"]["wild_cards"], **team_compare_kwargs),
    ]

    season_rows = [
        _build_compare_row("Wins", team1["selected_team"].get("wins"), team2["selected_team"].get("wins"), **team_compare_kwargs),
        _build_compare_row("Losses", team1["selected_team"].get("losses"), team2["selected_team"].get("losses"), better="lower", note="Lower is better.", **team_compare_kwargs),
        _build_compare_row("Win pct", team1["selected_team"].get("win_pct"), team2["selected_team"].get("win_pct"), display_formatter=_format_percentage, delta_formatter=_format_percentage, **team_compare_kwargs),
        _build_compare_row("Rank", team1["selected_team"].get("rank"), team2["selected_team"].get("rank"), better="lower", note="Lower is better.", **team_compare_kwargs),
        _build_compare_row("Run diff", team1["selected_team"].get("run_diff"), team2["selected_team"].get("run_diff"), display_formatter=_format_signed_number, delta_formatter=_format_number, **team_compare_kwargs),
        _build_compare_row("Team OPS", team1["selected_team"].get("ops"), team2["selected_team"].get("ops"), display_formatter=_format_rate, delta_formatter=_format_rate, **team_compare_kwargs),
        _build_compare_row("Attendance", team1["selected_team"].get("attendance"), team2["selected_team"].get("attendance"), **team_compare_kwargs),
    ]

    production_rows = [
        _build_compare_row("Runs", team1["selected_team"].get("runs"), team2["selected_team"].get("runs"), **team_compare_kwargs),
        _build_compare_row("Hits", team1["selected_team"].get("hits"), team2["selected_team"].get("hits"), **team_compare_kwargs),
        _build_compare_row("Home runs", team1["selected_team"].get("home_runs"), team2["selected_team"].get("home_runs"), **team_compare_kwargs),
        _build_compare_row("AVG", team1["selected_team"].get("avg"), team2["selected_team"].get("avg"), display_formatter=_format_rate, delta_formatter=_format_rate, **team_compare_kwargs),
        _build_compare_row("OBP", team1["selected_team"].get("obp"), team2["selected_team"].get("obp"), display_formatter=_format_rate, delta_formatter=_format_rate, **team_compare_kwargs),
        _build_compare_row("SLG", team1["selected_team"].get("slg"), team2["selected_team"].get("slg"), display_formatter=_format_rate, delta_formatter=_format_rate, **team_compare_kwargs),
        _build_compare_row("ERA", team1["selected_team"].get("era"), team2["selected_team"].get("era"), display_formatter=_format_era, delta_formatter=_format_era, better="lower", note="Lower is better.", **team_compare_kwargs),
        _build_compare_row("Pitching strikeouts", team1["selected_team"].get("strikeouts_pitching"), team2["selected_team"].get("strikeouts_pitching"), **team_compare_kwargs),
        _build_compare_row("Saves", team1["selected_team"].get("saves"), team2["selected_team"].get("saves"), **team_compare_kwargs),
    ]

    context_cards = [
        {
            "title": team1["name"],
            "value": team1["season_outcome"],
            "detail": f"{team1['league_name']} · {team1['division_name']} · {team1['year']}",
        },
        {
            "title": team2["name"],
            "value": team2["season_outcome"],
            "detail": f"{team2['league_name']} · {team2['division_name']} · {team2['year']}",
        },
    ]

    return [
        {
            "id": "franchise",
            "label": "Franchise",
            "icon": "bi-buildings-fill",
            "description": "Long-run franchise footprint across the recorded archive.",
            "rows": franchise_rows,
        },
        {
            "id": "season",
            "label": "Season",
            "icon": "bi-calendar-event-fill",
            "description": "Selected season performance and environment.",
            "rows": season_rows,
            "pair_cards": context_cards,
        },
        {
            "id": "production",
            "label": "Production",
            "icon": "bi-bar-chart-fill",
            "description": "Offense and pitching side-by-side for the selected season.",
            "rows": production_rows,
        },
    ]


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

    active_filters = _build_player_active_filters(
        search_term,
        selected_letter,
        birth_country,
        bats,
        throws,
        debut_decade,
        has_photo,
        filter_options,
    )

    if request.GET.get("fragment") == "catalog":
        return render(
            request,
            "partials/player_catalog.html",
            _build_players_catalog_context(
                request,
                selected_letter=selected_letter,
                search_term=search_term,
                birth_country=birth_country,
                bats=bats,
                throws=throws,
                debut_decade=debut_decade,
                sort=sort,
                has_photo=has_photo,
                active_filters=active_filters,
            ),
        )

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
        "total_players": None,
        "comparator_url": f"{reverse('compare_players')}?mode=players",
        "analytics_url": reverse("analytics"),
    }
    return render(request, "players.html", context)


def player_detail_view(request, player_id):
    player = _build_compare_profile(player_id)
    if not player:
        raise Http404("Player not found")
    player = attach_player_media(player)
    selected_players = _selected_compare_map(request, "player")
    player["compare_selected"] = player["player_id"] in selected_players
    detail_payload = _build_player_detail_payload(player)
    graph_payload = _build_player_graph_payload(player)

    try:
        rdf_triples = run_describe(BB_PLAYER_URI.format(player_id))
    except Exception:
        rdf_triples = []

    context = {
        "player": player,
        **detail_payload,
        **graph_payload,
        "rdf_triples": rdf_triples,
        "edit_state": build_player_edit_state(player, request.user.is_staff) if request.user.is_authenticated else None,
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
    selection = get_compare_selection(request)
    requested_mode = str(request.GET.get("mode", "")).strip().lower()
    letters = _alphabet()
    player1_letter = request.GET.get("player1_letter", "").strip().upper()
    player2_letter = request.GET.get("player2_letter", "").strip().upper()
    player1_term = request.GET.get("player1", "").strip()
    player2_term = request.GET.get("player2", "").strip()
    compare_kind = requested_mode if requested_mode in {"players", "teams"} else "players"

    if requested_mode not in {"players", "teams"} and selection["type"] == "team":
        compare_kind = "teams"

    if compare_kind == "teams":
        selected_items = selection["items"] if selection["type"] == "team" else []
        team1_item = selected_items[0] if len(selected_items) >= 1 else None
        team2_item = selected_items[1] if len(selected_items) >= 2 else None

        team1 = _build_team_compare_profile(team1_item["id"], team1_item.get("year", "")) if team1_item else None
        team2 = _build_team_compare_profile(team2_item["id"], team2_item.get("year", "")) if team2_item else None
        compare_ready = bool(team1 and team2)
        compare_tabs = _build_team_compare_tabs(team1, team2) if compare_ready else []
        compare_scoreboard = _build_compare_scoreboard(compare_tabs) if compare_tabs else None

        context = {
            "compare_kind": "teams",
            "team1": team1,
            "team2": team2,
            "compare_ready": compare_ready,
            "compare_tabs": compare_tabs,
            "compare_scoreboard": compare_scoreboard,
            "submitted": bool(team1_item or team2_item),
            "selection_count": len(selected_items),
            "selection_type": selection["type"],
        }
        return render(request, "compare.html", context)

    if not player1_term and not player2_term and selection["type"] == "player":
        selected_items = selection["items"]
        if len(selected_items) >= 1:
            player1_term = selected_items[0]["id"]
        if len(selected_items) >= 2:
            player2_term = selected_items[1]["id"]

    player1_options = get_player_options_by_initial(player1_letter) if player1_letter in letters else []
    player2_options = get_player_options_by_initial(player2_letter) if player2_letter in letters else []

    player1 = _build_compare_profile(player1_term) if player1_term else None
    player2 = _build_compare_profile(player2_term) if player2_term else None
    compare_ready = bool(player1 and player2)
    compare_tabs = _build_compare_tabs(player1, player2) if compare_ready else []
    compare_scoreboard = _build_compare_scoreboard(compare_tabs) if compare_tabs else None
    best_season_cards = _build_best_season_cards(player1, player2) if compare_ready else []

    context = {
        "compare_kind": "players",
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
        "selection_count": selection["count"] if selection["type"] == "player" else 0,
        "selection_type": selection["type"],
    }
    return render(request, "compare.html", context)


def graph_view(request):
    player_term = request.GET.get("player", "").strip()
    if player_term:
        target = reverse("player_detail", kwargs={"player_id": player_term})
        return redirect(f"{target}#relationship-graph")
    return redirect(reverse("players"))


@require_POST
def compare_selection_view(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    action = str(payload.get("action", "toggle")).strip().lower()
    if action == "clear":
        selection = clear_compare_selection(request)
        return JsonResponse(
            {
                "ok": True,
                "status": "cleared",
                "selection": selection,
            }
        )

    result = toggle_compare_selection(
        request,
        payload.get("item_type"),
        payload.get("item_id"),
        payload.get("label", ""),
        payload.get("year", ""),
    )
    return JsonResponse(result, status=200 if result.get("ok") else 400)

from collections import OrderedDict
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from .models import DataSuggestion, DataSuggestionChange
from .sparql import DIVISION_LABELS, ENDPOINT, LEAGUE_LABELS, escape_sparql_string


BB_NS = "http://baseball.ws.pt/"
XSD_NS = "http://www.w3.org/2001/XMLSchema#"
GRAPHDB_UPDATE_ENDPOINT = urlunsplit((*urlsplit(ENDPOINT)[:2], f"{urlsplit(ENDPOINT).path.rstrip('/')}/statements", "", ""))


PLAYER_FIELD_SPECS = OrderedDict(
    [
        ("display_name", {"label": "Player name", "type": "text", "predicate": "foaf:name", "scope": "player"}),
        ("birth_country", {"label": "Birth country", "type": "text", "predicate": "bb:birthCountry", "scope": "player"}),
        ("birth_state", {"label": "Birth state", "type": "text", "predicate": "bb:birthState", "scope": "player"}),
        ("birth_city", {"label": "Birth city", "type": "text", "predicate": "bb:birthCity", "scope": "player"}),
        (
            "bats",
            {
                "label": "Bats",
                "type": "choice",
                "predicate": "bb:bats",
                "scope": "player",
                "choices": [("R", "Right"), ("L", "Left"), ("B", "Switch"), ("", "Unknown")],
            },
        ),
        (
            "throws",
            {
                "label": "Throws",
                "type": "choice",
                "predicate": "bb:throws",
                "scope": "player",
                "choices": [("R", "Right"), ("L", "Left"), ("", "Unknown")],
            },
        ),
        ("debut", {"label": "Debut", "type": "date", "predicate": "bb:debut", "scope": "player"}),
        ("final_game", {"label": "Final game", "type": "date", "predicate": "bb:finalGame", "scope": "player"}),
    ]
)

TEAM_FIELD_SPECS = OrderedDict(
    [
        ("team_name", {"label": "Team name", "type": "text", "predicate": "bb:teamName", "scope": "team"}),
        ("franchise_name", {"label": "Franchise name", "type": "text", "predicate": "bb:franchiseName", "scope": "franchise"}),
        ("park", {"label": "Ballpark", "type": "text", "predicate": "bb:park", "scope": "team"}),
        (
            "league_code",
            {
                "label": "League",
                "type": "choice",
                "predicate": "bb:lgID",
                "scope": "team",
                "choices": [(code, name) for code, name in sorted(LEAGUE_LABELS.items())] + [("", "Unknown")],
            },
        ),
        (
            "division_code",
            {
                "label": "Division",
                "type": "choice",
                "predicate": "bb:divID",
                "scope": "team",
                "choices": [(code, name) for code, name in sorted(DIVISION_LABELS.items())] + [("", "Unknown")],
            },
        ),
        ("attendance", {"label": "Attendance", "type": "integer", "predicate": "bb:attendance", "scope": "team"}),
    ]
)

FIELD_SPECS = {
    DataSuggestion.ENTITY_PLAYER: PLAYER_FIELD_SPECS,
    DataSuggestion.ENTITY_TEAM: TEAM_FIELD_SPECS,
}


class SuggestionValidationError(ValueError):
    pass


def get_field_specs(entity_type):
    return FIELD_SPECS.get(entity_type, OrderedDict())


def build_player_edit_state(profile, is_admin):
    current_values = {
        "display_name": str(profile.get("name") or ""),
        "birth_country": str(profile.get("birth_country") or ""),
        "birth_state": str(profile.get("birth_state") or ""),
        "birth_city": str(profile.get("birth_city") or ""),
        "bats": str(profile.get("bats") or ""),
        "throws": str(profile.get("throws") or ""),
        "debut": str(profile.get("debut") or ""),
        "final_game": str(profile.get("final_game") or ""),
    }
    return _build_edit_state(
        entity_type=DataSuggestion.ENTITY_PLAYER,
        entity_id=str(profile.get("player_id") or ""),
        entity_year=None,
        current_values=current_values,
        is_admin=is_admin,
    )


def build_team_edit_state(team, is_admin):
    current_values = {
        "team_name": str(team.get("team_name") or ""),
        "franchise_name": str(team.get("franchise_name") or ""),
        "park": str(team.get("park") or ""),
        "league_code": str(team.get("league_code") or ""),
        "division_code": str(team.get("division_code") or ""),
        "attendance": "" if team.get("attendance") in (None, "") else str(int(team.get("attendance"))),
    }
    return _build_edit_state(
        entity_type=DataSuggestion.ENTITY_TEAM,
        entity_id=str(team.get("franchise_id") or ""),
        entity_year=team.get("year"),
        current_values=current_values,
        is_admin=is_admin,
    )


def _build_edit_state(*, entity_type, entity_id, entity_year, current_values, is_admin):
    fields = []
    for field_key, spec in get_field_specs(entity_type).items():
        fields.append(
            {
                "key": field_key,
                "label": spec["label"],
                "type": spec["type"],
                "value": current_values.get(field_key, ""),
                "display": display_field_value(entity_type, field_key, current_values.get(field_key, "")),
                "choices": [{"value": value, "label": label} for value, label in spec.get("choices", [])],
            }
        )
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_year": entity_year,
        "is_admin": bool(is_admin),
        "fields": fields,
        "current_values": current_values,
    }


def display_field_value(entity_type, field_key, value):
    spec = get_field_specs(entity_type).get(field_key)
    if not spec:
        return str(value or "")

    if value in (None, ""):
        return "N/A"

    if spec["type"] == "choice":
        return dict(spec.get("choices", [])).get(value, value)
    if spec["type"] == "integer":
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def normalize_submitted_changes(entity_type, raw_changes, current_values):
    specs = get_field_specs(entity_type)
    prepared = []

    if not isinstance(raw_changes, dict):
        raise SuggestionValidationError("Changes payload is invalid.")

    for field_key, raw_value in raw_changes.items():
        if field_key not in specs:
            raise SuggestionValidationError(f"Field '{field_key}' cannot be edited.")

        normalized_value = _normalize_field_value(specs[field_key], raw_value)
        current_value = str(current_values.get(field_key) or "")
        if normalized_value == current_value:
            continue

        prepared.append(
            {
                "field_key": field_key,
                "label": specs[field_key]["label"],
                "old_value": current_value,
                "new_value": normalized_value,
                "old_display": display_field_value(entity_type, field_key, current_value),
                "new_display": display_field_value(entity_type, field_key, normalized_value),
            }
        )

    if not prepared:
        raise SuggestionValidationError("No valid field changes were submitted.")

    return prepared


def _normalize_field_value(spec, raw_value):
    text = "" if raw_value is None else str(raw_value).strip()

    if spec["type"] == "text":
        return text
    if spec["type"] == "choice":
        allowed = {value for value, _label in spec.get("choices", [])}
        if text not in allowed:
            raise SuggestionValidationError(f"Invalid value for {spec['label']}.")
        return text
    if spec["type"] == "date":
        if not text:
            return ""
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise SuggestionValidationError(f"Invalid date for {spec['label']}.") from exc
        return text
    if spec["type"] == "integer":
        if not text:
            return ""
        try:
            value = int(text)
        except ValueError as exc:
            raise SuggestionValidationError(f"Invalid number for {spec['label']}.") from exc
        if value < 0:
            raise SuggestionValidationError(f"{spec['label']} cannot be negative.")
        return str(value)
    return text


def create_suggestion(*, submitted_by, entity_type, entity_id, entity_year, reason, changes, status=DataSuggestion.STATUS_PENDING, reviewed_by=None, review_note=""):
    suggestion = DataSuggestion.objects.create(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_year=entity_year,
        submitted_by=submitted_by,
        reason=reason,
        status=status,
        reviewed_by=reviewed_by,
        reviewed_at=timezone.now() if status != DataSuggestion.STATUS_PENDING else None,
        review_note=review_note,
    )
    DataSuggestionChange.objects.bulk_create(
        [
            DataSuggestionChange(
                suggestion=suggestion,
                field_key=change["field_key"],
                old_value=change["old_value"],
                new_value=change["new_value"],
            )
            for change in changes
        ]
    )
    return suggestion


def apply_suggestion_updates(entity_type, entity_id, entity_year, changes):
    if entity_type not in FIELD_SPECS:
        raise SuggestionValidationError("Unsupported entity type.")

    for change in changes:
        query = _build_update_query(
            entity_type=entity_type,
            entity_id=entity_id,
            entity_year=entity_year,
            field_key=change["field_key"],
            value=change["new_value"],
        )
        _run_graphdb_update(query)

    clear_sparql_caches()


def _build_update_query(*, entity_type, entity_id, entity_year, field_key, value):
    spec = get_field_specs(entity_type)[field_key]
    predicate = spec["predicate"]
    subject_selector = _subject_selector(entity_type, spec["scope"], entity_id, entity_year)
    current_var = "?currentValue"
    literal = _sparql_literal(spec, value)

    if literal is None:
        insert_block = ""
    else:
        insert_block = f"INSERT {{ ?subject {predicate} {literal} . }}\n"

    return f"""
PREFIX bb: <{BB_NS}>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
PREFIX xsd: <{XSD_NS}>

DELETE {{ ?subject {predicate} {current_var} . }}
{insert_block}WHERE {{
  {subject_selector}
  OPTIONAL {{ ?subject {predicate} {current_var} . }}
}}
""".strip()


def _subject_selector(entity_type, scope, entity_id, entity_year):
    safe_id = escape_sparql_string(entity_id)

    if entity_type == DataSuggestion.ENTITY_PLAYER and scope == "player":
        return f'?subject a bb:Player ; bb:playerID "{safe_id}" .'

    if entity_type == DataSuggestion.ENTITY_TEAM and scope == "franchise":
        return f'?subject a bb:Franchise ; bb:franchID "{safe_id}" .'

    if entity_type == DataSuggestion.ENTITY_TEAM and scope == "team":
        if not entity_year:
            raise SuggestionValidationError("Season year is required for team edits.")
        safe_year = escape_sparql_string(str(entity_year))
        return (
            f'?franchise a bb:Franchise ; bb:franchID "{safe_id}" . '
            f'?subject a bb:Team ; bb:franchiseOf ?franchise ; bb:yearID ?seasonYear . '
            f'FILTER(STR(?seasonYear) = "{safe_year}")'
        )

    raise SuggestionValidationError("Invalid update target.")


def _sparql_literal(spec, value):
    if value in (None, ""):
        return None

    safe_value = escape_sparql_string(value)
    if spec["type"] == "date":
        return f'"{safe_value}"^^xsd:date'
    if spec["type"] == "integer":
        return f'"{safe_value}"^^xsd:integer'
    return f'"{safe_value}"'


def _run_graphdb_update(query):
    payload = urlencode({"update": query}).encode("utf-8")
    request = Request(
        GRAPHDB_UPDATE_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30):
            return
    except (HTTPError, URLError) as exc:
        raise RuntimeError("GraphDB update failed.") from exc


def clear_sparql_caches():
    from . import sparql
    from . import team_branding

    for module in (sparql, team_branding):
        for attribute_name in dir(module):
            attribute = getattr(module, attribute_name)
            if hasattr(attribute, "cache_clear"):
                try:
                    attribute.cache_clear()
                except Exception:
                    continue

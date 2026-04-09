import json

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..edit_service import (
    SuggestionValidationError,
    apply_suggestion_updates,
    build_player_edit_state,
    build_team_edit_state,
    create_suggestion,
    display_field_value,
    get_field_specs,
    normalize_submitted_changes,
)
from ..models import DataSuggestion
from .players import _build_compare_profile
from .teams import _build_team_detail_context


def _json_error(message, *, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


def _entity_label(entity_type, edit_state):
    if entity_type == DataSuggestion.ENTITY_PLAYER:
        return edit_state["current_values"].get("display_name") or edit_state["entity_id"]
    team_name = edit_state["current_values"].get("team_name") or edit_state["entity_id"]
    year = edit_state.get("entity_year")
    if year:
        return f"{team_name} ({year})"
    return team_name


def _load_edit_state(entity_type, entity_id, entity_year, user):
    if entity_type == DataSuggestion.ENTITY_PLAYER:
        profile = _build_compare_profile(entity_id)
        if not profile:
            raise SuggestionValidationError("Player not found.")
        return build_player_edit_state(profile, user.is_staff)

    if entity_type == DataSuggestion.ENTITY_TEAM:
        detail_context = _build_team_detail_context(entity_id, str(entity_year or "").strip())
        team = detail_context.get("selected_team")
        if not team:
            raise SuggestionValidationError("Team not found.")
        return build_team_edit_state(team, user.is_staff)

    raise SuggestionValidationError("Unsupported entity type.")


def _parse_request_payload(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise SuggestionValidationError("Request payload is invalid.") from exc

    entity_type = str(payload.get("entity_type") or "").strip()
    entity_id = str(payload.get("entity_id") or "").strip()
    entity_year = payload.get("entity_year")
    reason = str(payload.get("reason") or "").strip()
    changes = payload.get("changes") or {}

    if not entity_type or not entity_id:
        raise SuggestionValidationError("Entity reference is missing.")

    if entity_year in ("", None):
        entity_year = None
    else:
        try:
            entity_year = int(entity_year)
        except (TypeError, ValueError) as exc:
            raise SuggestionValidationError("Season year is invalid.") from exc

    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "entity_year": entity_year,
        "reason": reason,
        "changes": changes,
    }


def _build_review_filters(status_value, entity_type_value):
    return {
        "status_options": [
            {"value": "", "label": "All statuses", "selected": not status_value},
            {
                "value": DataSuggestion.STATUS_PENDING,
                "label": "Pending",
                "selected": status_value == DataSuggestion.STATUS_PENDING,
            },
            {
                "value": DataSuggestion.STATUS_APPROVED,
                "label": "Approved",
                "selected": status_value == DataSuggestion.STATUS_APPROVED,
            },
            {
                "value": DataSuggestion.STATUS_REJECTED,
                "label": "Rejected",
                "selected": status_value == DataSuggestion.STATUS_REJECTED,
            },
        ],
        "entity_type_options": [
            {"value": "", "label": "All entities", "selected": not entity_type_value},
            {
                "value": DataSuggestion.ENTITY_PLAYER,
                "label": "Players",
                "selected": entity_type_value == DataSuggestion.ENTITY_PLAYER,
            },
            {
                "value": DataSuggestion.ENTITY_TEAM,
                "label": "Teams",
                "selected": entity_type_value == DataSuggestion.ENTITY_TEAM,
            },
        ],
    }


@require_POST
def suggestion_submit_view(request):
    if not request.user.is_authenticated:
        return _json_error("Login required.", status=403)
    if request.user.is_staff:
        return _json_error("Administrators should publish changes directly.", status=403)

    try:
        payload = _parse_request_payload(request)
        if not payload["reason"]:
            raise SuggestionValidationError("Please explain why these changes should be accepted.")
        edit_state = _load_edit_state(
            payload["entity_type"],
            payload["entity_id"],
            payload["entity_year"],
            request.user,
        )
        changes = normalize_submitted_changes(
            payload["entity_type"],
            payload["changes"],
            edit_state["current_values"],
        )
        suggestion = create_suggestion(
            submitted_by=request.user,
            entity_type=payload["entity_type"],
            entity_id=payload["entity_id"],
            entity_year=payload["entity_year"],
            reason=payload["reason"],
            changes=changes,
        )
    except SuggestionValidationError as exc:
        return _json_error(str(exc))

    return JsonResponse(
        {
            "ok": True,
            "message": "Suggestion submitted.",
            "suggestion_id": suggestion.id,
            "entity_label": _entity_label(payload["entity_type"], edit_state),
            "changes": [
                {
                    "field_key": change["field_key"],
                    "label": change["label"],
                    "old_display": change["old_display"],
                    "new_display": change["new_display"],
                }
                for change in changes
            ],
        }
    )


@require_POST
def suggestion_publish_view(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return _json_error("Administrator access required.", status=403)

    try:
        payload = _parse_request_payload(request)
        edit_state = _load_edit_state(
            payload["entity_type"],
            payload["entity_id"],
            payload["entity_year"],
            request.user,
        )
        changes = normalize_submitted_changes(
            payload["entity_type"],
            payload["changes"],
            edit_state["current_values"],
        )
        apply_suggestion_updates(
            payload["entity_type"],
            payload["entity_id"],
            payload["entity_year"],
            changes,
        )
        create_suggestion(
            submitted_by=request.user,
            entity_type=payload["entity_type"],
            entity_id=payload["entity_id"],
            entity_year=payload["entity_year"],
            reason="",
            changes=changes,
            status=DataSuggestion.STATUS_APPROVED,
            reviewed_by=request.user,
            review_note="Direct administrator edit.",
        )
    except SuggestionValidationError as exc:
        return _json_error(str(exc))
    except RuntimeError as exc:
        return _json_error(str(exc), status=502)

    return JsonResponse(
        {
            "ok": True,
            "message": "Changes published.",
            "entity_label": _entity_label(payload["entity_type"], edit_state),
            "updated_fields": [
                {
                    "field_key": change["field_key"],
                    "value": change["new_value"],
                    "display": change["new_display"],
                }
                for change in changes
            ],
        }
    )


@user_passes_test(lambda user: user.is_authenticated and user.is_staff)
def suggestions_review_view(request):
    status_filter = str(request.GET.get("status") or DataSuggestion.STATUS_PENDING).strip()
    entity_type_filter = str(request.GET.get("entity_type") or "").strip()

    queryset = DataSuggestion.objects.select_related("submitted_by", "reviewed_by").prefetch_related("changes")
    if status_filter in {
        DataSuggestion.STATUS_PENDING,
        DataSuggestion.STATUS_APPROVED,
        DataSuggestion.STATUS_REJECTED,
    }:
        queryset = queryset.filter(status=status_filter)
    else:
        status_filter = ""
    if entity_type_filter in {DataSuggestion.ENTITY_PLAYER, DataSuggestion.ENTITY_TEAM}:
        queryset = queryset.filter(entity_type=entity_type_filter)
    else:
        entity_type_filter = ""

    suggestions = []
    for suggestion in queryset:
        specs = get_field_specs(suggestion.entity_type)
        editable_changes = []
        for change in suggestion.changes.all():
            spec = specs.get(change.field_key, {})
            editable_changes.append(
                {
                    "id": change.id,
                    "field_key": change.field_key,
                    "label": spec.get("label", change.field_key),
                    "type": spec.get("type", "text"),
                    "value": change.new_value,
                    "old_display": display_field_value(suggestion.entity_type, change.field_key, change.old_value),
                    "new_display": display_field_value(suggestion.entity_type, change.field_key, change.new_value),
                    "choices": [{"value": value, "label": label} for value, label in spec.get("choices", [])],
                }
            )

        suggestion.editable_changes = editable_changes
        suggestions.append(suggestion)

    base_queryset = DataSuggestion.objects.all()
    counts = {
        "pending": base_queryset.filter(status=DataSuggestion.STATUS_PENDING).count(),
        "approved": base_queryset.filter(status=DataSuggestion.STATUS_APPROVED).count(),
        "rejected": base_queryset.filter(status=DataSuggestion.STATUS_REJECTED).count(),
    }

    context = {
        "suggestions": suggestions,
        "counts": counts,
        "active_status": status_filter or "",
        "active_entity_type": entity_type_filter or "",
        **_build_review_filters(status_filter, entity_type_filter),
    }
    return render(request, "suggestions_review.html", context)


@user_passes_test(lambda user: user.is_authenticated and user.is_staff)
@require_POST
def suggestion_approve_view(request, suggestion_id):
    suggestion = get_object_or_404(DataSuggestion.objects.prefetch_related("changes"), pk=suggestion_id)
    if suggestion.status != DataSuggestion.STATUS_PENDING:
        messages.error(request, "Only pending suggestions can be approved.")
        return redirect("suggestions_review")

    raw_changes = {}
    current_values = {}
    for change in suggestion.changes.all():
        raw_changes[change.field_key] = request.POST.get(f"change_{change.id}", change.new_value)
        current_values[change.field_key] = change.old_value

    try:
        prepared_changes = normalize_submitted_changes(suggestion.entity_type, raw_changes, current_values)
        apply_suggestion_updates(
            suggestion.entity_type,
            suggestion.entity_id,
            suggestion.entity_year,
            prepared_changes,
        )
    except SuggestionValidationError as exc:
        messages.error(request, str(exc))
        return redirect("suggestions_review")
    except RuntimeError as exc:
        messages.error(request, str(exc))
        return redirect("suggestions_review")

    for change in suggestion.changes.all():
        approved_value = next(
            (item["new_value"] for item in prepared_changes if item["field_key"] == change.field_key),
            change.new_value,
        )
        change.new_value = approved_value
        change.save(update_fields=["new_value"])

    suggestion.status = DataSuggestion.STATUS_APPROVED
    suggestion.review_note = str(request.POST.get("review_note") or "").strip()
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at"])
    messages.success(request, "Suggestion approved.")
    return redirect("suggestions_review")


def my_suggestions_view(request):
    if not request.user.is_authenticated:
        from django.shortcuts import redirect as _redirect
        return _redirect("login")

    queryset = (
        DataSuggestion.objects
        .filter(submitted_by=request.user)
        .prefetch_related("changes")
    )

    suggestions = []
    for suggestion in queryset:
        specs = get_field_specs(suggestion.entity_type)
        changes = []
        for change in suggestion.changes.all():
            spec = specs.get(change.field_key, {})
            changes.append(
                {
                    "label": spec.get("label", change.field_key),
                    "old_display": display_field_value(suggestion.entity_type, change.field_key, change.old_value),
                    "new_display": display_field_value(suggestion.entity_type, change.field_key, change.new_value),
                }
            )
        suggestion.display_changes = changes
        suggestions.append(suggestion)

    return render(request, "my_suggestions.html", {"suggestions": suggestions})


@user_passes_test(lambda user: user.is_authenticated and user.is_staff)
@require_POST
def suggestion_reject_view(request, suggestion_id):
    suggestion = get_object_or_404(DataSuggestion, pk=suggestion_id)
    if suggestion.status != DataSuggestion.STATUS_PENDING:
        messages.error(request, "Only pending suggestions can be rejected.")
        return redirect("suggestions_review")

    suggestion.status = DataSuggestion.STATUS_REJECTED
    suggestion.review_note = str(request.POST.get("review_note") or "").strip()
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at"])
    messages.success(request, "Suggestion rejected.")
    return redirect("suggestions_review")

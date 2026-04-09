import json

from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from ..models import QuizAttempt
from ..quiz_service import (
    QUIZ_SESSION_KEY,
    answer_round_question,
    build_round_state,
    get_round_state_payload,
    round_state_is_valid,
)


def _serialize_leaderboard_entry(entry, rank):
    return {
        "rank": rank,
        "user_id": entry["user_id"],
        "username": entry["user__username"],
        "best_score": entry["best_score"],
        "best_percentage": entry["best_percentage"],
        "attempts": entry["attempts"],
        "last_played": entry["last_played"].strftime("%Y-%m-%d %H:%M") if entry["last_played"] else "",
    }


def _get_quiz_leaderboard_payload(current_user=None, limit=10):
    aggregate_rows = list(
        QuizAttempt.objects.values("user_id", "user__username")
        .annotate(
            best_score=Max("score"),
            best_percentage=Max("percentage"),
            attempts=Count("id"),
            last_played=Max("completed_at"),
        )
        .order_by("-best_score", "-best_percentage", "-last_played", "user__username")
    )

    top_entries = [
        _serialize_leaderboard_entry(entry, rank)
        for rank, entry in enumerate(aggregate_rows[:limit], start=1)
    ]

    current_user_entry = None
    if current_user and current_user.is_authenticated:
        for rank, entry in enumerate(aggregate_rows, start=1):
            if entry["user_id"] == current_user.id:
                current_user_entry = _serialize_leaderboard_entry(entry, rank)
                break

    return {
        "entries": top_entries,
        "current_user_entry": current_user_entry,
        "has_scores": bool(aggregate_rows),
    }


def _persist_completed_quiz_attempt(request, summary):
    if not request.user.is_authenticated:
        return

    QuizAttempt.objects.create(
        user=request.user,
        score=summary["score"],
        total_questions=summary["total_questions"],
        percentage=summary["percentage"],
    )


@ensure_csrf_cookie
def quiz_view(request):
    return render(
        request,
        "quiz.html",
        {
            "quiz_leaderboard": _get_quiz_leaderboard_payload(request.user),
        },
    )


@ensure_csrf_cookie
def quiz_play_view(request):
    return render(request, "quiz_play.html")


@require_POST
def quiz_start_api_view(request):
    try:
        round_state = build_round_state()
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=503)
    except Exception:
        return JsonResponse({"error": "Could not start the quiz right now."}, status=500)

    request.session[QUIZ_SESSION_KEY] = round_state
    request.session.modified = True
    return JsonResponse(get_round_state_payload(round_state))


@require_POST
def quiz_answer_api_view(request):
    round_state = request.session.get(QUIZ_SESSION_KEY)
    if not round_state or not round_state_is_valid(round_state):
        request.session.pop(QUIZ_SESSION_KEY, None)
        request.session.modified = True
        return JsonResponse(
            {
                "error": "No active round. Start a new quiz.",
                "requires_restart": True,
            },
            status=409,
        )

    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = {}

    question_id = str(payload.get("question_id", "")).strip()
    selected_option_id = str(payload.get("selected_option_id", "")).strip()
    if not question_id or not selected_option_id:
        return JsonResponse(
            {
                "error": "Question id and selected option id are required.",
                "requires_restart": False,
            },
            status=400,
        )

    try:
        response_payload = answer_round_question(round_state, question_id, selected_option_id)
    except ValueError as exc:
        return JsonResponse(
            {
                "error": str(exc),
                "requires_restart": True,
            },
            status=409,
        )
    except Exception:
        return JsonResponse(
            {
                "error": "Could not submit that answer right now.",
                "requires_restart": False,
            },
            status=500,
        )

    request.session[QUIZ_SESSION_KEY] = round_state
    request.session.modified = True

    if response_payload.get("completed") and response_payload.get("summary"):
        _persist_completed_quiz_attempt(request, response_payload["summary"])
        response_payload["leaderboard"] = _get_quiz_leaderboard_payload(request.user)

    return JsonResponse(response_payload)


@require_GET
def quiz_state_api_view(request):
    try:
        round_state = request.session.get(QUIZ_SESSION_KEY)
        if round_state and not round_state_is_valid(round_state):
            request.session.pop(QUIZ_SESSION_KEY, None)
            request.session.modified = True
            round_state = None
        payload = get_round_state_payload(round_state)
        if payload.get("completed"):
            payload["leaderboard"] = _get_quiz_leaderboard_payload(request.user)
        return JsonResponse(payload)
    except Exception:
        return JsonResponse({"error": "Could not restore the quiz state."}, status=500)

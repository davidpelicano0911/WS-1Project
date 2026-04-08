import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from ..quiz_service import (
    QUIZ_SESSION_KEY,
    answer_round_question,
    build_round_state,
    get_round_state_payload,
    round_state_is_valid,
)


def quiz_view(request):
    return render(request, "quiz.html")


@require_POST
def quiz_start_api_view(request):
    try:
        round_state = build_round_state()
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=503)

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

    request.session[QUIZ_SESSION_KEY] = round_state
    request.session.modified = True
    return JsonResponse(response_payload)


@require_GET
def quiz_state_api_view(request):
    round_state = request.session.get(QUIZ_SESSION_KEY)
    if round_state and not round_state_is_valid(round_state):
        request.session.pop(QUIZ_SESSION_KEY, None)
        request.session.modified = True
        round_state = None
    return JsonResponse(get_round_state_payload(round_state))

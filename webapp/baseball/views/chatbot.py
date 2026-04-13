from django.http import JsonResponse

from ..chatbot import answer_chat_message


def chatbot_ask_view(request):
    query = (request.GET.get("q") or "").strip()
    try:
        payload = answer_chat_message(query)
    except Exception:
        payload = {
            "answer": "The assistant could not reach GraphDB right now. Start the repository and try again.",
            "items": [],
            "suggestions": [
                "Show AL teams",
                "Players from Cuba",
                "Awards in 2015",
                "Top salaries",
            ],
        }
    payload["query"] = query
    return JsonResponse(payload)

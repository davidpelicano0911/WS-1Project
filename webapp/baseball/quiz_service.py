from concurrent.futures import ThreadPoolExecutor
import random
from copy import deepcopy
from functools import lru_cache
from uuid import uuid4

from .sparql import (
    LEAGUE_LABELS,
    ask_quiz_award_answer,
    ask_quiz_leaderboard_answer,
    ask_quiz_salary_answer,
    get_quiz_award_bank,
    get_quiz_leaderboard_bank,
    get_quiz_salary_bank,
)


QUIZ_SESSION_KEY = "quiz_round_v3"
ROUND_SIZE = 10

QUESTION_FAMILY_TARGETS = {
    "leaderboard": 5,
    "salary": 2,
    "award": 3,
}

ROUND_LEADERBOARD_STAT_COUNT = 1

LEADERBOARD_CONFIG = {
    "home_runs": {
        "category": "Home runs",
        "prompt_label": "home runs",
        "value_label": "home runs",
    },
    "rbi": {
        "category": "RBI",
        "prompt_label": "RBI",
        "value_label": "RBI",
    },
    "strikeouts": {
        "category": "Strikeouts",
        "prompt_label": "strikeouts",
        "value_label": "strikeouts",
    },
}


def _format_number(value):
    if value is None:
        return "N/A"
    return f"{int(value):,}"


def _format_currency(value):
    if value is None:
        return "N/A"
    return f"${int(value):,}"


def _league_label(code):
    code = str(code or "").strip().upper()
    if not code or code == "ML":
        return "Major League Baseball"
    return LEAGUE_LABELS.get(code, code)


def _dedupe_option_labels(options):
    label_counts = {}
    for option in options:
        label_counts[option["label"]] = label_counts.get(option["label"], 0) + 1

    normalized = []
    for option in options:
        item = dict(option)
        if label_counts[item["label"]] > 1:
            item["label"] = f"{item['label']} ({item['id'].replace('player:', '')})"
        normalized.append(item)
    return normalized


def _build_options_from_players(players, detail_formatter=None):
    unique_players = []
    seen_player_ids = set()
    for player in players:
        player_id = str(player.get("player_id", "")).strip()
        if not player_id or player_id in seen_player_ids:
            continue
        seen_player_ids.add(player_id)
        unique_players.append(player)
        if len(unique_players) >= 4:
            break

    options = [
        {
            "id": f"player:{player['player_id']}",
            "label": player["name"],
            "detail": detail_formatter(player["value"]) if detail_formatter and player.get("value") is not None else "",
        }
        for player in unique_players
    ]
    return _dedupe_option_labels(options)


def _shuffle_options(question):
    shuffled = dict(question)
    options = list(question["options"])
    random.shuffle(options)
    shuffled["options"] = options
    return shuffled


def _question_has_unique_options(question):
    options = question.get("options", [])
    option_ids = [str(option.get("id", "")).strip() for option in options]
    correct_option_id = str(question.get("correct_option_id", "")).strip()
    return (
        len(options) == 4
        and len(set(option_ids)) == 4
        and all(option_ids)
        and correct_option_id in option_ids
    )


def round_state_is_valid(round_state):
    if not isinstance(round_state, dict):
        return False

    questions = round_state.get("questions")
    current_index = round_state.get("current_index")
    total_questions = round_state.get("total_questions")
    if not isinstance(questions, list) or not questions:
        return False
    if not isinstance(current_index, int) or current_index < 0:
        return False
    if not isinstance(total_questions, int) or total_questions <= 0:
        return False
    if len(questions) < total_questions:
        return False

    return all(_question_has_unique_options(question) for question in questions)


def build_leaderboard_questions(stat_keys=None):
    questions = []
    selected_stat_keys = stat_keys or tuple(LEADERBOARD_CONFIG.keys())
    for stat_key in selected_stat_keys:
        config = LEADERBOARD_CONFIG.get(stat_key)
        if not config:
            continue
        for entry in get_quiz_leaderboard_bank(stat_key):
            leaders = entry["leaders"][:4]
            if len(leaders) < 4:
                continue
            if leaders[0]["value"] == leaders[1]["value"]:
                continue

            league_name = _league_label(entry["league_code"])
            leader = leaders[0]
            question = {
                "id": f"leaderboard:{stat_key}:{entry['league_code']}:{entry['year']}",
                "family": "leaderboard",
                "prompt": f"Who led the {league_name} in {config['prompt_label']} in {entry['year']}?",
                "category": config["category"],
                "context": f"{league_name} · {entry['year']}",
                "options": _build_options_from_players(leaders, _format_number),
                "correct_option_id": f"player:{leader['player_id']}",
                "explanation": (
                    f"{leader['name']} led the {league_name} with "
                    f"{_format_number(leader['value'])} {config['value_label']} in {entry['year']}."
                ),
                "answer_check": {
                    "kind": "leaderboard",
                    "stat_key": stat_key,
                    "league_code": entry["league_code"],
                    "year": entry["year"],
                },
            }
            if len(question["options"]) < 4:
                continue
            questions.append(_shuffle_options(question))
    return questions


def build_salary_questions():
    questions = []
    for entry in get_quiz_salary_bank():
        leaders = entry["leaders"][:4]
        if len(leaders) < 4:
            continue
        if leaders[0]["value"] == leaders[1]["value"]:
            continue

        leader = leaders[0]
        question = {
            "id": f"salary:{entry['year']}",
            "family": "salary",
            "prompt": f"Who had the highest recorded salary in {entry['year']}?",
            "category": "Salaries",
            "context": f"Salary leaderboard · {entry['year']}",
            "options": _build_options_from_players(leaders, _format_currency),
            "correct_option_id": f"player:{leader['player_id']}",
            "explanation": (
                f"{leader['name']} had the highest recorded salary in {entry['year']} "
                f"at {_format_currency(leader['value'])}."
            ),
            "answer_check": {
                "kind": "salary",
                "year": entry["year"],
            },
        }
        if len(question["options"]) < 4:
            continue
        questions.append(_shuffle_options(question))
    return questions


def _nearest_winners(winners, target_index, limit=3):
    target_year = winners[target_index]["year"]
    candidates = [
        winner
        for idx, winner in enumerate(winners)
        if idx != target_index
    ]
    candidates.sort(key=lambda winner: (abs(winner["year"] - target_year), -winner["year"]))
    return candidates[:limit]


def build_award_questions():
    questions = []
    for group in get_quiz_award_bank():
        winners = group["winners"]
        if len(winners) < 4:
            continue

        award_name = group["award_name"]
        league_code = group["league_code"]
        league_name = _league_label(league_code)

        for index, winner in enumerate(winners):
            distractors = _nearest_winners(winners, index)
            if len(distractors) < 3:
                continue

            prompt = f"Who won the {award_name} in {winner['year']}?"
            explanation = f"{winner['name']} won the {award_name} in {winner['year']}."
            if league_code and league_code != "ML":
                prompt = f"Who won the {league_name} {award_name} in {winner['year']}?"
                explanation = f"{winner['name']} won the {league_name} {award_name} in {winner['year']}."

            options = _build_options_from_players([winner, *distractors])
            if len(options) < 4:
                continue
            question = {
                "id": f"award:{award_name}:{league_code}:{winner['year']}",
                "family": "award",
                "prompt": prompt,
                "category": "Awards",
                "context": f"{award_name} · {winner['year']}",
                "options": options,
                "correct_option_id": f"player:{winner['player_id']}",
                "explanation": explanation,
                "answer_check": {
                    "kind": "award",
                    "award_name": award_name,
                    "league_code": league_code,
                    "year": winner["year"],
                },
            }
            questions.append(_shuffle_options(question))
    return questions


@lru_cache(maxsize=8)
def _get_cached_question_families(leaderboard_stats=None):
    if leaderboard_stats:
        selected_leaderboard_stats = tuple(sorted(leaderboard_stats))
    else:
        selected_leaderboard_stats = tuple(LEADERBOARD_CONFIG.keys())

    with ThreadPoolExecutor(max_workers=3) as executor:
        leaderboard_future = executor.submit(build_leaderboard_questions, selected_leaderboard_stats)
        salary_future = executor.submit(build_salary_questions)
        award_future = executor.submit(build_award_questions)
        families = {
            "leaderboard": leaderboard_future.result(),
            "salary": salary_future.result(),
            "award": award_future.result(),
        }
    return {
        family: [question for question in questions if _question_has_unique_options(question)]
        for family, questions in families.items()
    }


def get_quiz_question_families(leaderboard_stats=None):
    return deepcopy(_get_cached_question_families(leaderboard_stats))


def get_quiz_question_pool():
    families = get_quiz_question_families()
    questions = []
    for family_questions in families.values():
        questions.extend(family_questions)
    return questions


def _public_question_payload(question, question_number, total_questions):
    return {
        "id": question["id"],
        "prompt": question["prompt"],
        "category": question["category"],
        "context": question["context"],
        "question_number": question_number,
        "total_questions": total_questions,
        "options": question["options"],
    }


def _option_player_id(option_id):
    text = str(option_id or "").strip()
    if not text.startswith("player:"):
        return ""
    return text.split(":", 1)[1].strip()


def _ask_question_is_correct(question, selected_option_id):
    answer_check = question.get("answer_check") or {}
    selected_player_id = _option_player_id(selected_option_id)
    if not selected_player_id:
        return False

    kind = answer_check.get("kind")
    if kind == "leaderboard":
        return ask_quiz_leaderboard_answer(
            answer_check.get("stat_key"),
            answer_check.get("league_code"),
            answer_check.get("year"),
            selected_player_id,
        )
    if kind == "salary":
        return ask_quiz_salary_answer(answer_check.get("year"), selected_player_id)
    if kind == "award":
        return ask_quiz_award_answer(
            answer_check.get("award_name"),
            answer_check.get("league_code"),
            answer_check.get("year"),
            selected_player_id,
        )

    return selected_option_id == question.get("correct_option_id")


def _build_summary(round_state):
    total = round_state["total_questions"]
    score = round_state["score"]
    percentage = round((score / total) * 100) if total else 0
    if percentage >= 90:
        copy = "Elite round."
    elif percentage >= 70:
        copy = "Strong round."
    elif percentage >= 50:
        copy = "Solid base."
    else:
        copy = "Try again to improve your score."

    return {
        "score": score,
        "total_questions": total,
        "percentage": percentage,
        "copy": copy,
    }


def build_round_state(question_count=ROUND_SIZE):
    leaderboard_keys = tuple(
        random.sample(
            list(LEADERBOARD_CONFIG.keys()),
            k=min(ROUND_LEADERBOARD_STAT_COUNT, len(LEADERBOARD_CONFIG)),
        )
    )
    families = get_quiz_question_families(leaderboard_keys)
    selected = []
    used_ids = set()

    for family, target_count in QUESTION_FAMILY_TARGETS.items():
        candidates = list(families.get(family, []))
        random.shuffle(candidates)
        for question in candidates:
            if question["id"] in used_ids:
                continue
            selected.append(question)
            used_ids.add(question["id"])
            if len([item for item in selected if item["family"] == family]) >= target_count:
                break

    if len(selected) < question_count:
        remaining = [
            question
            for question in get_quiz_question_pool()
            if question["id"] not in used_ids
        ]
        random.shuffle(remaining)
        for question in remaining:
            selected.append(question)
            used_ids.add(question["id"])
            if len(selected) >= question_count:
                break

    if len(selected) < question_count:
        raise ValueError("Not enough quiz questions are available.")

    random.shuffle(selected)
    final_questions = selected[:question_count]
    return {
        "round_id": uuid4().hex,
        "questions": final_questions,
        "current_index": 0,
        "answers": [],
        "score": 0,
        "completed": False,
        "total_questions": question_count,
    }


def get_round_state_payload(round_state):
    if not round_state:
        return {"active": False}

    payload = {
        "active": True,
        "round_id": round_state["round_id"],
        "score": round_state["score"],
        "answered": len(round_state["answers"]),
        "total_questions": round_state["total_questions"],
        "completed": round_state["completed"],
    }
    if round_state["completed"]:
        payload["summary"] = _build_summary(round_state)
        return payload

    question = round_state["questions"][round_state["current_index"]]
    payload["current_question"] = _public_question_payload(
        question,
        round_state["current_index"] + 1,
        round_state["total_questions"],
    )
    return payload


def answer_round_question(round_state, question_id, selected_option_id):
    if not round_state or round_state.get("completed"):
        raise ValueError("No active round. Start a new quiz.")

    current_index = round_state["current_index"]
    questions = round_state["questions"]
    if current_index >= len(questions):
        raise ValueError("This round is already complete.")

    question = questions[current_index]
    if question["id"] != question_id:
        raise ValueError("That question is no longer active. Refresh the quiz state.")
    if not _question_has_unique_options(question):
        raise ValueError("This round is outdated. Start a new quiz.")

    valid_option_ids = {option["id"] for option in question["options"]}
    if selected_option_id not in valid_option_ids:
        raise ValueError("That answer option is invalid.")

    is_correct = _ask_question_is_correct(question, selected_option_id)
    round_state["answers"].append(
        {
            "question_id": question_id,
            "selected_option_id": selected_option_id,
            "correct_option_id": question["correct_option_id"],
            "is_correct": is_correct,
        }
    )
    if is_correct:
        round_state["score"] += 1

    round_state["current_index"] += 1
    if round_state["current_index"] >= round_state["total_questions"]:
        round_state["completed"] = True

    payload = {
        "ok": True,
        "is_correct": is_correct,
        "selected_option_id": selected_option_id,
        "correct_option_id": question["correct_option_id"],
        "explanation": question["explanation"],
        "score": round_state["score"],
        "answered": len(round_state["answers"]),
        "total_questions": round_state["total_questions"],
        "completed": round_state["completed"],
    }
    if round_state["completed"]:
        payload["summary"] = _build_summary(round_state)
    else:
        next_question = questions[round_state["current_index"]]
        payload["next_question"] = _public_question_payload(
            next_question,
            round_state["current_index"] + 1,
            round_state["total_questions"],
        )
    return payload

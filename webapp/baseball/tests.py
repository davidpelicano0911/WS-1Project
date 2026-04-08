from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse

from baseball.models import QuizAttempt
from baseball.quiz_service import (
    QUIZ_SESSION_KEY,
    _get_cached_question_families,
    answer_round_question,
    build_award_questions,
    build_leaderboard_questions,
    build_round_state,
)


def _sample_question(question_id, family="leaderboard", correct_option_id="player:a"):
    return {
        "id": question_id,
        "family": family,
        "prompt": f"Prompt for {question_id}",
        "category": family.title(),
        "context": "Context",
        "options": [
            {"id": "player:a", "label": "Player A"},
            {"id": "player:b", "label": "Player B"},
            {"id": "player:c", "label": "Player C"},
            {"id": "player:d", "label": "Player D"},
        ],
        "correct_option_id": correct_option_id,
        "explanation": f"Explanation for {question_id}",
    }


class QuizServiceTests(TestCase):
    def tearDown(self):
        _get_cached_question_families.cache_clear()

    @patch("baseball.quiz_service.get_quiz_leaderboard_bank")
    def test_leaderboard_questions_have_four_unique_options(self, mock_bank):
        mock_bank.return_value = [
            {
                "league_code": "AL",
                "year": 2015,
                "leaders": [
                    {"player_id": "alpha01", "name": "Alpha", "value": 42},
                    {"player_id": "bravo01", "name": "Bravo", "value": 39},
                    {"player_id": "charl01", "name": "Charlie", "value": 38},
                    {"player_id": "delta01", "name": "Delta", "value": 36},
                ],
            }
        ]

        questions = build_leaderboard_questions()

        self.assertEqual(len(questions), 3)
        question = questions[0]
        self.assertIn("Who led the American League", question["prompt"])
        self.assertEqual(len(question["options"]), 4)
        self.assertEqual(len({option["id"] for option in question["options"]}), 4)
        self.assertEqual(
            sum(1 for option in question["options"] if option["id"] == question["correct_option_id"]),
            1,
        )

    @patch("baseball.quiz_service.get_quiz_award_bank")
    def test_award_questions_use_same_award_pool(self, mock_bank):
        mock_bank.return_value = [
            {
                "award_name": "Cy Young Award",
                "league_code": "AL",
                "winners": [
                    {"year": 2012, "player_id": "p1", "name": "One"},
                    {"year": 2013, "player_id": "p2", "name": "Two"},
                    {"year": 2014, "player_id": "p3", "name": "Three"},
                    {"year": 2015, "player_id": "p4", "name": "Four"},
                ],
            }
        ]

        questions = build_award_questions()

        self.assertEqual(len(questions), 4)
        question = questions[-1]
        self.assertIn("Cy Young Award", question["prompt"])
        self.assertEqual(len(question["options"]), 4)
        self.assertEqual(len({option["id"] for option in question["options"]}), 4)
        self.assertTrue(question["explanation"].endswith("2015."))

    @patch("baseball.quiz_service.get_quiz_award_bank")
    def test_award_questions_skip_duplicate_winner_options(self, mock_bank):
        mock_bank.return_value = [
            {
                "award_name": "Cy Young Award",
                "league_code": "NL",
                "winners": [
                    {"year": 1992, "player_id": "maddugr01", "name": "Greg Maddux"},
                    {"year": 1993, "player_id": "maddugr01", "name": "Greg Maddux"},
                    {"year": 1994, "player_id": "maddugr01", "name": "Greg Maddux"},
                    {"year": 1995, "player_id": "maddugr01", "name": "Greg Maddux"},
                    {"year": 1996, "player_id": "smoltjo01", "name": "John Smoltz"},
                    {"year": 1997, "player_id": "glavito02", "name": "Tom Glavine"},
                    {"year": 1998, "player_id": "brownke01", "name": "Kevin Brown"},
                ],
            }
        ]

        questions = build_award_questions()

        self.assertTrue(questions)
        for question in questions:
            self.assertEqual(len(question["options"]), 4)
            self.assertEqual(len({option["id"] for option in question["options"]}), 4)

    @patch("baseball.quiz_service.get_quiz_question_families")
    def test_build_round_state_avoids_duplicate_questions(self, mock_families):
        mock_families.return_value = {
            "leaderboard": [_sample_question(f"leader:{idx}", family="leaderboard") for idx in range(6)],
            "salary": [_sample_question(f"salary:{idx}", family="salary") for idx in range(3)],
            "award": [_sample_question(f"award:{idx}", family="award") for idx in range(4)],
        }

        round_state = build_round_state()

        self.assertEqual(round_state["total_questions"], 10)
        self.assertEqual(len(round_state["questions"]), 10)
        self.assertEqual(len({question["id"] for question in round_state["questions"]}), 10)

    def test_answer_round_question_increments_score_only_when_correct(self):
        round_state = {
            "round_id": "round-1",
            "questions": [
                _sample_question("q1", correct_option_id="player:a"),
                _sample_question("q2", correct_option_id="player:b"),
            ],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 2,
        }

        payload_one = answer_round_question(round_state, "q1", "player:a")
        payload_two = answer_round_question(round_state, "q2", "player:c")

        self.assertTrue(payload_one["is_correct"])
        self.assertFalse(payload_two["is_correct"])
        self.assertEqual(round_state["score"], 1)
        self.assertTrue(round_state["completed"])


class QuizViewTests(TestCase):
    def test_quiz_page_renders(self):
        response = self.client.get(reverse("quiz"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Baseball Quiz")
        self.assertContains(response, "Top quiz scores")

    @patch("baseball.views.quiz.build_round_state")
    def test_start_api_creates_round_in_session(self, mock_build_round_state):
        mock_build_round_state.return_value = {
            "round_id": "round-1",
            "questions": [_sample_question("q1"), _sample_question("q2")],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 2,
        }

        response = self.client.post(
            reverse("quiz_start_api"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[QUIZ_SESSION_KEY]["round_id"], "round-1")
        self.assertEqual(response.json()["current_question"]["id"], "q1")

    def test_answer_api_updates_score(self):
        session = self.client.session
        session[QUIZ_SESSION_KEY] = {
            "round_id": "round-1",
            "questions": [_sample_question("q1", correct_option_id="player:a")],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 1,
        }
        session.save()

        response = self.client.post(
            reverse("quiz_answer_api"),
            data='{"question_id":"q1","selected_option_id":"player:a"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["is_correct"])
        self.assertEqual(payload["score"], 1)
        self.assertTrue(payload["completed"])

    def test_completed_round_persists_attempt_for_authenticated_user(self):
        user = User.objects.create_user(username="quizfan", password="StrongPass123!")
        self.client.force_login(user)
        session = self.client.session
        session[QUIZ_SESSION_KEY] = {
            "round_id": "round-1",
            "questions": [_sample_question("q1", correct_option_id="player:a")],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 1,
        }
        session.save()

        response = self.client.post(
            reverse("quiz_answer_api"),
            data='{"question_id":"q1","selected_option_id":"player:a"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        attempt = QuizAttempt.objects.get(user=user)
        self.assertEqual(attempt.score, 1)
        self.assertEqual(attempt.percentage, 100)
        self.assertIn("leaderboard", response.json())

    def test_completed_round_does_not_persist_attempt_for_anonymous_user(self):
        session = self.client.session
        session[QUIZ_SESSION_KEY] = {
            "round_id": "round-1",
            "questions": [_sample_question("q1", correct_option_id="player:a")],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 1,
        }
        session.save()

        response = self.client.post(
            reverse("quiz_answer_api"),
            data='{"question_id":"q1","selected_option_id":"player:a"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(QuizAttempt.objects.count(), 0)

    def test_answer_api_without_round_returns_recoverable_error(self):
        response = self.client.post(
            reverse("quiz_answer_api"),
            data='{"question_id":"q1","selected_option_id":"player:a"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        payload = response.json()
        self.assertTrue(payload["requires_restart"])

    def test_state_api_restores_current_question(self):
        session = self.client.session
        session[QUIZ_SESSION_KEY] = {
            "round_id": "round-1",
            "questions": [_sample_question("q1"), _sample_question("q2")],
            "current_index": 1,
            "answers": [{"question_id": "q1", "selected_option_id": "player:a", "is_correct": True}],
            "score": 1,
            "completed": False,
            "total_questions": 2,
        }
        session.save()

        response = self.client.get(reverse("quiz_state_api"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["active"])
        self.assertEqual(payload["score"], 1)
        self.assertEqual(payload["current_question"]["id"], "q2")

    def test_state_api_drops_invalid_round_with_duplicate_options(self):
        session = self.client.session
        bad_question = _sample_question("q1")
        bad_question["options"][2]["id"] = "player:b"
        bad_question["options"][2]["label"] = "Player B"
        session[QUIZ_SESSION_KEY] = {
            "round_id": "round-1",
            "questions": [bad_question],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 1,
        }
        session.save()

        response = self.client.get(reverse("quiz_state_api"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["active"])


class AuthViewTests(TestCase):
    def test_default_users_exist(self):
        normal_user = User.objects.get(username="user")
        admin_user = User.objects.get(username="admin")

        self.assertFalse(normal_user.is_staff)
        self.assertFalse(normal_user.is_superuser)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(check_password("password", normal_user.password))
        self.assertTrue(check_password("password", admin_user.password))

    def test_register_creates_normal_user_and_logs_in(self):
        response = self.client.post(
            reverse("register"),
            {
                "username": "normalfan",
                "email": "fan@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username="normalfan")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_login_view_authenticates_user(self):
        user = User.objects.create_user(username="slugger", email="slugger@example.com", password="StrongPass123!")

        response = self.client.post(
            reverse("login"),
            {
                "username": "slugger",
                "password": "StrongPass123!",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.id)

    def test_logout_view_clears_session(self):
        user = User.objects.create_user(username="slugger", password="StrongPass123!")
        self.client.force_login(user)

        response = self.client.get(reverse("logout"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_home_shows_admin_role_for_staff_user(self):
        admin_user = User.objects.create_user(
            username="adminfan",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Administrator")
        self.assertContains(response, "Logout")

    def test_home_shows_login_and_register_for_anonymous_user(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, "Login")
        self.assertContains(response, "Register")

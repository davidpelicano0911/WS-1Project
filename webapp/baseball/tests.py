from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.urls import reverse
from rdflib import Graph, Literal, Namespace
from rdflib.namespace import FOAF, RDF

from baseball.models import DataSuggestion, QuizAttempt
from baseball.quiz_service import (
    QUIZ_SESSION_KEY,
    _get_cached_question_families,
    answer_round_question,
    build_award_questions,
    build_leaderboard_questions,
    build_round_state,
)
from baseball.sparql_queries.graphs import get_player_graph_data, get_team_graph_data
from baseball.sparql_queries.misc import (
    get_awards_timeline,
    get_franchise_history,
    get_hall_of_fame_timeline,
    get_salary_trends,
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


BB = Namespace("http://baseball.ws.pt/")


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

    @patch("baseball.quiz_service.ask_quiz_leaderboard_answer")
    def test_answer_round_question_uses_ask_for_leaderboard_questions(self, mock_ask):
        mock_ask.return_value = True
        round_state = {
            "round_id": "round-1",
            "questions": [
                {
                    **_sample_question("q1", correct_option_id="player:a"),
                    "answer_check": {
                        "kind": "leaderboard",
                        "stat_key": "home_runs",
                        "league_code": "AL",
                        "year": 2005,
                    },
                }
            ],
            "current_index": 0,
            "answers": [],
            "score": 0,
            "completed": False,
            "total_questions": 1,
        }

        payload = answer_round_question(round_state, "q1", "player:b")

        self.assertTrue(payload["is_correct"])
        mock_ask.assert_called_once_with("home_runs", "AL", 2005, "b")


class PlayerGraphQueryTests(TestCase):
    def tearDown(self):
        get_player_graph_data.cache_clear()

    @patch("baseball.sparql_queries.graphs.run_construct")
    def test_player_graph_uses_constructed_semantic_neighborhood(self, mock_run_construct):
        graph = Graph()

        player = BB["player/aaronha01"]
        team = BB["team/ATL/1974"]
        franchise = BB["franchise/ATL"]
        award = BB["award/mvp/1957"]
        league = BB["graph/league/NL"]
        teammate = BB["player/mayswi01"]
        manager = BB["player/coxbo01"]

        graph.add((player, RDF.type, BB.GraphPlayer))
        graph.add((player, BB.playerID, Literal("aaronha01")))
        graph.add((player, FOAF.name, Literal("Hank Aaron")))

        graph.add((team, RDF.type, BB.GraphTeam))
        graph.add((team, BB.teamName, Literal("Atlanta Braves")))
        graph.add((team, BB.teamID, Literal("ATL")))
        graph.add((team, BB.yearID, Literal("1974")))

        graph.add((franchise, RDF.type, BB.GraphFranchise))
        graph.add((franchise, BB.franchiseName, Literal("Atlanta Braves")))

        graph.add((award, RDF.type, BB.GraphAward))
        graph.add((award, BB.awardName, Literal("MVP Award")))
        graph.add((award, BB.yearID, Literal("1957")))

        graph.add((league, RDF.type, BB.GraphLeague))
        graph.add((league, BB.lgID, Literal("NL")))

        graph.add((teammate, RDF.type, BB.GraphTeammate))
        graph.add((teammate, FOAF.name, Literal("Willie Mays")))
        graph.add((teammate, BB.sharedSeasons, Literal("2")))

        graph.add((manager, RDF.type, BB.GraphManager))
        graph.add((manager, FOAF.name, Literal("Bobby Cox")))

        graph.add((player, BB.playedFor, team))
        graph.add((team, BB.franchiseLink, franchise))
        graph.add((team, BB.leagueLink, league))
        graph.add((player, BB.playedInLeague, league))
        graph.add((player, BB.wonGraphAward, award))
        graph.add((player, BB.sharedClubhouseWith, teammate))
        graph.add((team, BB.managedByPerson, manager))

        mock_run_construct.return_value = graph

        graph_data = get_player_graph_data("aaronha01")

        node_types = {node["data"]["type"] for node in graph_data["nodes"]}
        edge_labels = {edge["data"]["label"] for edge in graph_data["edges"]}

        self.assertSetEqual(
            node_types,
            {"player", "team", "franchise", "award", "league", "teammate", "manager"},
        )
        self.assertIn("played for", edge_labels)
        self.assertIn("franchise", edge_labels)
        self.assertIn("league", edge_labels)
        self.assertIn("won", edge_labels)
        self.assertIn("teammate", edge_labels)
        self.assertIn("managed by", edge_labels)


class TeamGraphQueryTests(TestCase):
    def tearDown(self):
        get_team_graph_data.cache_clear()

    @patch("baseball.sparql_queries.graphs.run_construct")
    def test_team_graph_uses_constructed_team_neighborhood(self, mock_run_construct):
        graph = Graph()

        team = BB["team/ATL/1974"]
        franchise = BB["franchise/ATL"]
        league = BB["graph/league/NL"]
        player = BB["player/aaronha01"]
        manager = BB["player/coxbo01"]
        award = BB["award/mvp/1974"]

        graph.add((team, RDF.type, BB.GraphFocusTeam))
        graph.add((team, BB.teamName, Literal("Atlanta Braves")))
        graph.add((team, BB.teamID, Literal("ATL")))
        graph.add((team, BB.teamIDBR, Literal("ATL")))
        graph.add((team, BB.yearID, Literal("1974")))

        graph.add((franchise, RDF.type, BB.GraphFranchise))
        graph.add((franchise, BB.franchiseName, Literal("Atlanta Braves")))

        graph.add((league, RDF.type, BB.GraphLeague))
        graph.add((league, BB.lgID, Literal("NL")))

        graph.add((player, RDF.type, BB.GraphRosterPlayer))
        graph.add((player, FOAF.name, Literal("Hank Aaron")))

        graph.add((manager, RDF.type, BB.GraphManager))
        graph.add((manager, FOAF.name, Literal("Bobby Cox")))

        graph.add((award, RDF.type, BB.GraphAward))
        graph.add((award, BB.awardName, Literal("MVP Award")))
        graph.add((award, BB.yearID, Literal("1974")))

        graph.add((team, BB.franchiseLink, franchise))
        graph.add((team, BB.leagueLink, league))
        graph.add((team, BB.rosterLink, player))
        graph.add((team, BB.managedByPerson, manager))
        graph.add((player, BB.wonGraphAward, award))

        mock_run_construct.return_value = graph

        graph_data = get_team_graph_data("ATL", 1974)

        node_types = {node["data"]["type"] for node in graph_data["nodes"]}
        edge_labels = {edge["data"]["label"] for edge in graph_data["edges"]}

        self.assertSetEqual(
            node_types,
            {"focus-team", "franchise", "league", "player", "manager", "award"},
        )
        self.assertIn("franchise", edge_labels)
        self.assertIn("league", edge_labels)
        self.assertIn("roster", edge_labels)
        self.assertIn("managed by", edge_labels)
        self.assertIn("won", edge_labels)


class AnalyticsQueryTests(TestCase):
    def tearDown(self):
        get_salary_trends.cache_clear()
        get_franchise_history.cache_clear()
        get_awards_timeline.cache_clear()
        get_hall_of_fame_timeline.cache_clear()

    @patch("baseball.sparql_queries.misc.run_query")
    def test_salary_trends_transform_rows_into_sorted_numeric_payload(self, mock_run_query):
        mock_run_query.return_value = [
            {
                "year": {"value": "2001"},
                "totalSalary": {"value": "3000000"},
                "avgSalary": {"value": "1500000.5"},
                "maxSalary": {"value": "2000000"},
                "paidPlayers": {"value": "2"},
            },
            {
                "year": {"value": "1999"},
                "totalSalary": {"value": "1000000"},
                "avgSalary": {"value": "500000"},
                "maxSalary": {"value": "700000"},
                "paidPlayers": {"value": "3"},
            },
        ]

        trends = get_salary_trends()

        self.assertEqual([row["year"] for row in trends], [1999, 2001])
        self.assertEqual(trends[1]["total_salary"], 3000000)
        self.assertEqual(trends[1]["avg_salary"], 1500000.5)
        self.assertEqual(trends[1]["max_salary"], 2000000)
        self.assertEqual(trends[1]["paid_players"], 2)

    @patch("baseball.sparql_queries.misc.run_query")
    def test_franchise_history_computes_win_pct_and_run_diff(self, mock_run_query):
        mock_run_query.return_value = [
            {
                "franchID": {"value": "ATL"},
                "franchName": {"value": "Atlanta Braves"},
                "year": {"value": "1998"},
                "wins": {"value": "106"},
                "losses": {"value": "56"},
                "runs": {"value": "795"},
                "runsAllowed": {"value": "595"},
            }
        ]

        history = get_franchise_history()

        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["franch_id"], "ATL")
        self.assertEqual(history[0]["franch_name"], "Atlanta Braves")
        self.assertEqual(history[0]["run_diff"], 200)
        self.assertAlmostEqual(history[0]["win_pct"], 0.654, places=3)

    @patch("baseball.sparql_queries.misc.run_query")
    def test_awards_timeline_keeps_award_and_league_dimensions(self, mock_run_query):
        mock_run_query.return_value = [
            {
                "year": {"value": "2005"},
                "awardName": {"value": "MVP"},
                "league": {"value": "AL"},
                "awardCount": {"value": "1"},
            },
            {
                "year": {"value": "2006"},
                "awardName": {"value": "MVP"},
                "awardCount": {"value": "1"},
            },
        ]

        timeline = get_awards_timeline()

        self.assertEqual(timeline[0]["award_name"], "MVP")
        self.assertEqual(timeline[0]["league"], "AL")
        self.assertEqual(timeline[1]["league"], "")
        self.assertEqual(timeline[1]["count"], 1)

    @patch("baseball.sparql_queries.misc.run_query")
    def test_hall_timeline_computes_weighted_vote_pct_and_skips_zero_division(self, mock_run_query):
        mock_run_query.return_value = [
            {
                "year": {"value": "1995"},
                "inductedCount": {"value": "3"},
                "totalVotes": {"value": "900"},
                "totalBallots": {"value": "1200"},
            },
            {
                "year": {"value": "1996"},
                "inductedCount": {"value": "1"},
                "totalVotes": {"value": "0"},
                "totalBallots": {"value": "0"},
            },
        ]

        timeline = get_hall_of_fame_timeline()

        self.assertEqual(timeline[0]["inducted_count"], 3)
        self.assertEqual(timeline[0]["vote_pct"], 75.0)
        self.assertIsNone(timeline[1]["vote_pct"])


class QuizViewTests(TestCase):
    def test_quiz_page_renders(self):
        response = self.client.get(reverse("quiz"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Baseball Quiz")
        self.assertContains(response, "Top quiz scores")
        self.assertNotContains(response, "Guest mode")

    def test_quiz_play_page_renders(self):
        response = self.client.get(reverse("quiz_play"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live round")
        self.assertContains(response, "Baseball Quiz")

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


class AnalyticsViewTests(TestCase):
    @patch("baseball.views.stats.get_managers_list")
    @patch("baseball.views.stats.get_hall_of_fame_timeline")
    @patch("baseball.views.stats.get_hall_of_fame_members")
    @patch("baseball.views.stats.get_award_league_options")
    @patch("baseball.views.stats.get_award_options")
    @patch("baseball.views.stats.get_award_year_options")
    @patch("baseball.views.stats.get_awards_timeline")
    @patch("baseball.views.stats.get_awards_catalog")
    @patch("baseball.views.stats.get_awards_list")
    @patch("baseball.views.stats.get_franchise_history")
    @patch("baseball.views.stats.get_franchise_options")
    @patch("baseball.views.stats.get_salary_trends")
    @patch("baseball.views.stats.get_top_salaries")
    @patch("baseball.views.stats.get_global_team_leaders")
    @patch("baseball.views.stats.get_global_player_leaders")
    def test_analytics_view_exposes_graph_context_and_renders_controls(
        self,
        mock_global_players,
        mock_global_teams,
        mock_top_salaries,
        mock_salary_trends,
        mock_franchise_options,
        mock_franchise_history,
        mock_awards_list,
        mock_awards_catalog,
        mock_awards_timeline,
        mock_award_years,
        mock_award_options,
        mock_award_leagues,
        mock_hall_members,
        mock_hall_timeline,
        mock_managers,
    ):
        mock_global_players.return_value = {"hr": [], "rbi": [], "strikeouts": []}
        mock_global_teams.return_value = [{"franch_id": "ATL", "name": "Atlanta Braves", "wins": 100}]
        mock_top_salaries.return_value = [{"name": {"value": "Player One"}, "salary": {"value": "4000000"}, "year": {"value": "2001"}}]
        mock_salary_trends.return_value = [{"year": 2001, "total_salary": 4000000, "avg_salary": 2000000.0, "max_salary": 4000000, "paid_players": 2}]
        mock_franchise_options.return_value = [{"franch_id": "ATL", "name": "Atlanta Braves"}]
        mock_franchise_history.return_value = [{"franch_id": "ATL", "franch_name": "Atlanta Braves", "year": 2001, "wins": 88, "losses": 74, "runs": 799, "runs_allowed": 677, "win_pct": 0.543, "run_diff": 122}]
        mock_awards_list.return_value = [{"player_id": "p1", "name": "Player One", "award_name": "MVP", "year": 2001, "league": "AL"}]
        mock_awards_catalog.return_value = [{"player_id": "p1", "name": "Player One", "award_name": "MVP", "year": 2001, "league": "AL"}]
        mock_awards_timeline.return_value = [{"year": 2001, "award_name": "MVP", "league": "AL", "count": 1}]
        mock_award_years.return_value = [{"year": 2001}]
        mock_award_options.return_value = [{"award_name": "MVP"}]
        mock_award_leagues.return_value = [{"league": "AL"}]
        mock_hall_members.return_value = [{"player_id": "p1", "name": "Player One", "year": 2001, "percent": "75.0%"}]
        mock_hall_timeline.return_value = [{"year": 2001, "inducted_count": 1, "vote_pct": 75.0}]
        mock_managers.return_value = [{"player_id": "m1", "name": "Manager One", "wins": 100, "win_pct": ".600"}]

        response = self.client.get(reverse("analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("salary_trends", response.context)
        self.assertIn("franchise_history", response.context)
        self.assertIn("awards_timeline", response.context)
        self.assertIn("hall_timeline", response.context)
        self.assertEqual(response.context["default_franchise_id"], "ATL")
        self.assertContains(response, 'id="analytics-salary-trends-data"', html=False)
        self.assertContains(response, 'id="analytics-franchise-select"', html=False)
        self.assertContains(response, 'id="analytics-league-filter"', html=False)
        self.assertContains(response, 'id="analytics-awards-table-year"', html=False)
        self.assertContains(response, 'id="analytics-awards-table-award"', html=False)
        self.assertContains(response, 'id="analytics-awards-pagination"', html=False)
        self.assertContains(response, 'id="analytics-hall-chart"', html=False)
        self.assertContains(response, 'id="analytics-awards-catalog-data"', html=False)

    @patch("baseball.views.stats.get_managers_list", return_value=[])
    @patch("baseball.views.stats.get_hall_of_fame_timeline", return_value=[])
    @patch("baseball.views.stats.get_hall_of_fame_members", return_value=[])
    @patch("baseball.views.stats.get_award_league_options", return_value=[])
    @patch("baseball.views.stats.get_award_options", return_value=[])
    @patch("baseball.views.stats.get_award_year_options", return_value=[])
    @patch("baseball.views.stats.get_awards_timeline", return_value=[])
    @patch("baseball.views.stats.get_awards_catalog", return_value=[])
    @patch("baseball.views.stats.get_awards_list", return_value=[])
    @patch("baseball.views.stats.get_franchise_history", return_value=[])
    @patch("baseball.views.stats.get_franchise_options", return_value=[])
    @patch("baseball.views.stats.get_salary_trends", return_value=[])
    @patch("baseball.views.stats.get_top_salaries", return_value=[])
    @patch("baseball.views.stats.get_global_team_leaders", return_value=[])
    @patch("baseball.views.stats.get_global_player_leaders", return_value={"hr": [], "rbi": [], "strikeouts": []})
    def test_analytics_view_renders_chart_empty_states(self, *_mocks):
        response = self.client.get(reverse("analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No salary trend data is available for charting.")
        self.assertContains(response, "No franchise history data is available for charting.")
        self.assertContains(response, "No awards timeline data is available for charting.")
        self.assertContains(response, "No Hall of Fame timeline data is available for charting.")


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


class SuggestionWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="fan", password="StrongPass123!")
        self.admin = User.objects.create_user(
            username="staffer",
            password="StrongPass123!",
            is_staff=True,
            is_superuser=True,
        )

    def _player_edit_state(self):
        return {
            "entity_type": DataSuggestion.ENTITY_PLAYER,
            "entity_id": "alpha01",
            "entity_year": None,
            "is_admin": False,
            "fields": [],
            "current_values": {
                "display_name": "Alpha Player",
                "birth_country": "USA",
                "birth_state": "CA",
                "birth_city": "Los Angeles",
                "bats": "R",
                "throws": "R",
                "debut": "2001-04-05",
                "final_game": "",
            },
        }

    def _team_edit_state(self):
        return {
            "entity_type": DataSuggestion.ENTITY_TEAM,
            "entity_id": "BOS",
            "entity_year": 2004,
            "is_admin": False,
            "fields": [],
            "current_values": {
                "team_name": "Boston Red Sox",
                "franchise_name": "Boston Red Sox",
                "park": "Fenway Park",
                "league_code": "AL",
                "division_code": "E",
                "attendance": "3200000",
            },
        }

    @patch("baseball.views.suggestions._load_edit_state")
    def test_normal_user_can_submit_player_suggestion(self, mock_load_edit_state):
        self.client.force_login(self.user)
        mock_load_edit_state.return_value = self._player_edit_state()

        response = self.client.post(
            reverse("suggestion_submit"),
            data='{"entity_type":"player","entity_id":"alpha01","changes":{"birth_city":"San Diego","throws":"L"},"reason":"Official profile lists a different city and throwing hand."}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        suggestion = DataSuggestion.objects.get()
        self.assertEqual(suggestion.status, DataSuggestion.STATUS_PENDING)
        self.assertEqual(suggestion.entity_type, DataSuggestion.ENTITY_PLAYER)
        self.assertEqual(suggestion.reason, "Official profile lists a different city and throwing hand.")
        self.assertEqual(suggestion.changes.count(), 2)

    @patch("baseball.views.suggestions._load_edit_state")
    def test_normal_user_can_submit_team_suggestion(self, mock_load_edit_state):
        self.client.force_login(self.user)
        mock_load_edit_state.return_value = self._team_edit_state()

        response = self.client.post(
            reverse("suggestion_submit"),
            data='{"entity_type":"team","entity_id":"BOS","entity_year":2004,"changes":{"park":"New Fenway"},"reason":"Park label is outdated."}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        suggestion = DataSuggestion.objects.get()
        self.assertEqual(suggestion.entity_type, DataSuggestion.ENTITY_TEAM)
        self.assertEqual(suggestion.entity_year, 2004)
        self.assertEqual(suggestion.changes.first().field_key, "park")

    @patch("baseball.views.suggestions._load_edit_state")
    def test_invalid_non_editable_field_is_rejected(self, mock_load_edit_state):
        self.client.force_login(self.user)
        mock_load_edit_state.return_value = self._player_edit_state()

        response = self.client.post(
            reverse("suggestion_submit"),
            data='{"entity_type":"player","entity_id":"alpha01","changes":{"height":"72"},"reason":"Bad field."}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DataSuggestion.objects.count(), 0)

    @patch("baseball.views.suggestions._load_edit_state")
    def test_explanation_is_required_for_normal_user_submission(self, mock_load_edit_state):
        self.client.force_login(self.user)
        mock_load_edit_state.return_value = self._player_edit_state()

        response = self.client.post(
            reverse("suggestion_submit"),
            data='{"entity_type":"player","entity_id":"alpha01","changes":{"birth_city":"San Diego"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DataSuggestion.objects.count(), 0)

    def test_staff_can_access_review_queue_and_normal_user_cannot(self):
        user_response = self.client.get(reverse("suggestions_review"))
        self.assertEqual(user_response.status_code, 302)

        self.client.force_login(self.user)
        normal_response = self.client.get(reverse("suggestions_review"))
        self.assertEqual(normal_response.status_code, 302)

        self.client.force_login(self.admin)
        admin_response = self.client.get(reverse("suggestions_review"))
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, "User suggestions")

    @patch("baseball.views.suggestions.apply_suggestion_updates")
    def test_staff_can_approve_suggestion(self, mock_apply_updates):
        suggestion = DataSuggestion.objects.create(
            entity_type=DataSuggestion.ENTITY_PLAYER,
            entity_id="alpha01",
            submitted_by=self.user,
            reason="Fix it",
        )
        change = suggestion.changes.create(field_key="birth_city", old_value="Los Angeles", new_value="San Diego")

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("suggestion_approve", args=[suggestion.id]),
            {f"change_{change.id}": "San Francisco", "review_note": "Confirmed against source."},
        )

        self.assertEqual(response.status_code, 302)
        suggestion.refresh_from_db()
        change.refresh_from_db()
        self.assertEqual(suggestion.status, DataSuggestion.STATUS_APPROVED)
        self.assertEqual(suggestion.reviewed_by, self.admin)
        self.assertEqual(change.new_value, "San Francisco")
        mock_apply_updates.assert_called_once()

    def test_staff_can_reject_suggestion(self):
        suggestion = DataSuggestion.objects.create(
            entity_type=DataSuggestion.ENTITY_TEAM,
            entity_id="BOS",
            entity_year=2004,
            submitted_by=self.user,
            reason="Reject me",
        )
        suggestion.changes.create(field_key="park", old_value="Fenway Park", new_value="Wrong Park")

        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("suggestion_reject", args=[suggestion.id]),
            {"review_note": "Does not match source."},
        )

        self.assertEqual(response.status_code, 302)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, DataSuggestion.STATUS_REJECTED)
        self.assertEqual(suggestion.reviewed_by, self.admin)

    @patch("baseball.views.suggestions.apply_suggestion_updates")
    @patch("baseball.views.suggestions._load_edit_state")
    def test_staff_direct_publish_creates_approved_audit_record(self, mock_load_edit_state, mock_apply_updates):
        self.client.force_login(self.admin)
        admin_state = self._player_edit_state()
        admin_state["is_admin"] = True
        mock_load_edit_state.return_value = admin_state

        response = self.client.post(
            reverse("suggestion_publish"),
            data='{"entity_type":"player","entity_id":"alpha01","changes":{"display_name":"Alpha Prime"}}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        suggestion = DataSuggestion.objects.get()
        self.assertEqual(suggestion.status, DataSuggestion.STATUS_APPROVED)
        self.assertEqual(suggestion.reviewed_by, self.admin)
        mock_apply_updates.assert_called_once()

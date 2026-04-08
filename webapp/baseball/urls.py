from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('players/', views.players_view, name='players'),
    path('players/<str:player_id>/graph-photo/', views.player_graph_photo_view, name='player_graph_photo'),
    path('players/<str:player_id>/', views.player_detail_view, name='player_detail'),
    path('teams/', views.teams_view, name='teams'),
    path('teams/league/<str:league_code>/', views.league_detail_view, name='league_detail'),
    path('teams/<str:franchise_id>/', views.team_detail_view, name='team_detail'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('quiz/', views.quiz_view, name='quiz'),
    path('quiz/api/start/', views.quiz_start_api_view, name='quiz_start_api'),
    path('quiz/api/answer/', views.quiz_answer_api_view, name='quiz_answer_api'),
    path('quiz/api/state/', views.quiz_state_api_view, name='quiz_state_api'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('about/', views.about_view, name='about'),
    path('awards/', views.awards_view, name='awards_list'),
    path('salaries/', views.salaries_view, name='salaries_list'),
    path('compare/', views.compare_players_view, name='compare_players'),
    path('graph/', views.graph_view, name='graph_view'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('search/', views.portal_search_view, name='portal_search'),
    path('players/', views.players_view, name='players'),
    path('players/<str:player_id>/', views.player_detail_view, name='player_detail'),
    path('teams/', views.teams_view, name='teams'),
    path('teams/league/<str:league_code>/', views.league_detail_view, name='league_detail'),
    path('teams/<str:franchise_id>/', views.team_detail_view, name='team_detail'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('about/', views.about_view, name='about'),
    path('awards/', views.awards_view, name='awards_list'),
    path('salaries/', views.salaries_view, name='salaries_list'),
    path('compare/', views.compare_players_view, name='compare_players'),
    path('compare/selection/', views.compare_selection_view, name='compare_selection'),
    path('graph/', views.graph_view, name='graph_view'),
]

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('players/', views.players_view, name='players'),
    path('teams/', views.teams_view, name='teams'),
    path('analytics/', views.analytics_view, name='analytics'),
    path('about/', views.about_view, name='about'),
    path('awards/', views.awards_view, name='awards_list'),
    path('salaries/', views.salaries_view, name='salaries_list'),
    path('compare/', views.compare_players_view, name='compare_players'),
    path('graph/', views.graph_view, name='graph_view'),
]

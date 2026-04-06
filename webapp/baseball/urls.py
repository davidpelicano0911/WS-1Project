from django.urls import path
from . import views

urlpatterns = [
    # Rota para a página inicial (Home)
    path('', views.home, name='home'),
    # Rota para a página de prémios que planeámos
    path('awards/', views.awards_view, name='awards_list'),
    path('salaries/', views.salaries_view, name='salaries_list'),
    path('compare/', views.compare_players_view, name='compare_players'),
    path('graph/', views.graph_view, name='graph_view'),
]

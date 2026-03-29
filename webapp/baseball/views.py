from django.shortcuts import render
from .sparql import get_top_salaries, get_awards_list

def home(request):
    return render(request, 'index.html')

def awards_view(request):
    awards = get_awards_list()
    return render(request, 'awards.html', {'awards': awards})

# ADICIONA ESTA FUNÇÃO:
def salaries_view(request):
    salaries = get_top_salaries()
    return render(request, 'salaries.html', {'salaries': salaries})
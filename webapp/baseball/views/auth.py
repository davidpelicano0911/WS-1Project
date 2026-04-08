from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from ..forms import LoginForm, RegisterForm


def _safe_redirect_target(request, fallback="home"):
    next_url = str(request.GET.get("next") or request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return fallback


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Logged in.")
        redirect_target = _safe_redirect_target(request)
        if redirect_target == "home":
            return redirect("home")
        return redirect(redirect_target)

    return render(
        request,
        "login.html",
        {
            "form": form,
            "next_url": _safe_redirect_target(request, fallback=""),
        },
    )


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created.")
        return redirect("home")

    return render(request, "register.html", {"form": form})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out.")
    return redirect("home")

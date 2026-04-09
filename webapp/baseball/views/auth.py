from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from ..forms import LoginForm, RegisterForm


def _safe_redirect_target(request, fallback="home"):
    next_url = str(request.GET.get("next") or request.POST.get("next") or "").strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return fallback


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _error_payload(form):
    return {
        "non_field_errors": list(form.non_field_errors()),
        "field_errors": {field: [str(error) for error in errors] for field, errors in form.errors.items()},
    }


def login_view(request):
    if request.user.is_authenticated:
        if _is_ajax(request):
            return JsonResponse({"ok": True, "redirect_url": "/"})
        return redirect("home")

    use_modal_prefix = _is_ajax(request)
    form = LoginForm(request, data=request.POST or None, prefix="login" if use_modal_prefix else None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        messages.success(request, "Logged in.")
        redirect_target = _safe_redirect_target(request)
        if _is_ajax(request):
            return JsonResponse({"ok": True, "redirect_url": "/" if redirect_target == "home" else redirect_target})
        if redirect_target == "home":
            return redirect("home")
        return redirect(redirect_target)

    if request.method == "POST" and _is_ajax(request):
        return JsonResponse(
            {
                "ok": False,
                "tab": "login",
                "errors": _error_payload(form),
            }
        )

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
        if _is_ajax(request):
            return JsonResponse({"ok": True, "redirect_url": "/"})
        return redirect("home")

    use_modal_prefix = _is_ajax(request)
    form = RegisterForm(request.POST or None, prefix="register" if use_modal_prefix else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created.")
        redirect_target = _safe_redirect_target(request)
        if _is_ajax(request):
            return JsonResponse({"ok": True, "redirect_url": "/" if redirect_target == "home" else redirect_target})
        if redirect_target == "home":
            return redirect("home")
        return redirect(redirect_target)

    if request.method == "POST" and _is_ajax(request):
        return JsonResponse(
            {
                "ok": False,
                "tab": "register",
                "errors": _error_payload(form),
            }
        )

    return render(request, "register.html", {"form": form, "next_url": _safe_redirect_target(request, fallback="")})


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Logged out.")
    return redirect("home")

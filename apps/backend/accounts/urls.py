"""Mounted at `dashboard/`. `login/` and `demo/` are the only public dashboard paths."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("demo/", views.demo_view, name="demo"),
    path("logout/", views.logout_view, name="logout"),
]

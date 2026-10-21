"""Mounted at `dashboard/`, after `accounts.urls`. Every view is wrapped in `@staff_required`."""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview_view, name="overview"),
]

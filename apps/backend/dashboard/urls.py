"""Mounted at `dashboard/`, after `accounts.urls`. Every view is wrapped in `@staff_required`."""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path("bookings/", views.bookings_view, name="bookings"),
    path("bookings/<str:reference>/", views.booking_detail_view, name="booking_detail"),
    path("schedule/", views.schedule_view, name="schedule"),
    path("schedule/new/", views.new_view, name="new"),
    path("schedule/booking/<str:reference>/", views.booking_panel, name="booking"),
    path("schedule/booking/<str:reference>/cancel/", views.cancel_view, name="cancel"),
]

from django.urls import include, path
from django.views.generic import RedirectView

from core import views

urlpatterns = [
    path("healthz", views.healthz),
    path("webhooks/", include("payments.urls")),
    path("api/v1/", include("storefront.urls")),
    # Sign-in, demo and sign-out. Keep it before the dashboard pages' own include.
    path("dashboard/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("", RedirectView.as_view(url="/dashboard/")),
]

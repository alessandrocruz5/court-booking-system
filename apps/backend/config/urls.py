from django.urls import include, path

from core import views

urlpatterns = [
    path("healthz", views.healthz),
    path("webhooks/", include("payments.urls")),
    path("api/v1/", include("storefront.urls")),
]

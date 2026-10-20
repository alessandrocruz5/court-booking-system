from django.urls import path

from storefront import views

urlpatterns = [
    path("catalog", views.catalog),
    path("availability", views.availability_view),
    path("bookings", views.create_booking),
    path("bookings/lookup", views.booking_lookup),
    path("checkout/confirm", views.checkout_confirm),
    path("checkout/release", views.checkout_release),
]

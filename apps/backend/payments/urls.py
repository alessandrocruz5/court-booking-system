from django.urls import path

from payments import views

urlpatterns = [
    path("paymongo", views.paymongo_webhook),
]

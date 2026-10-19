from django.urls import path

from . import views

urlpatterns = [
    path("mfa/", views.mfa, name="mfa"),
]

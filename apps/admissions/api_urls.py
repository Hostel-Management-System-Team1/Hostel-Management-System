from django.urls import path

from . import api

urlpatterns = [
    path("applications", api.ApplicationCreateView.as_view(), name="api-applications"),
]

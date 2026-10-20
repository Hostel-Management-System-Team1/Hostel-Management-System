from django.urls import path

from . import api

urlpatterns = [
    path("applications", api.ApplicationCreateView.as_view(), name="api-applications"),
    path("allocations", api.AllocationCreateView.as_view(), name="api-allocations"),
]

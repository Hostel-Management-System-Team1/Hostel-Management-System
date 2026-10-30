"""REST API, mounted at /api/v1/ (SAD 4.3). Each service module adds its own urls here."""

from django.urls import include, path

urlpatterns = [
    path("", include("apps.accounts.api_urls")),
    path("", include("apps.admissions.api_urls")),
    path("", include("apps.fees.api_urls")),
    path("", include("apps.gate.api_urls")),
]
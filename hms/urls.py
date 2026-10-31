from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("m/<slug:slug>/", views.module_page, name="module"),
    path("profile/", views.profile, name="profile"),

    path("", include("apps.admissions.urls")),
    path("", include("apps.fees.urls")),

    path("accounts/", include("apps.accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),

    path("api/v1/", include("hms.api_urls")),

    path("mess/", include("apps.mess.urls")),
    path("complaints/", include("apps.complaints.urls")),

    path("reports/", include("apps.reporting.urls")),

    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("m/<slug:slug>/", views.module_page, name="module"),
    path("profile/", views.profile, name="profile"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

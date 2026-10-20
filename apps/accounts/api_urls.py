from django.urls import path

from . import api

urlpatterns = [
    path("me", api.MeView.as_view(), name="api-me"),
    path("users", api.UserListView.as_view(), name="api-users"),
]

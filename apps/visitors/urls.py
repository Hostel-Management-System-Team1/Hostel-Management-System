from django.urls import path

from . import views

app_name = "visitors"

urlpatterns = [
    path("", views.visitor_list, name="list"),
    path("register/", views.visitor_register, name="register"),
    path("<int:pk>/entry/", views.visitor_entry, name="entry"),
    path("<int:pk>/exit/", views.visitor_exit, name="exit"),
    path("<int:pk>/override/", views.visitor_override, name="override"),
]

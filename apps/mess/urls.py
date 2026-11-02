from django.urls import path

from . import views

app_name = "mess"

urlpatterns = [
    path("", views.mess_home, name="home"),
    path("meal/", views.meal_save, name="meal_save"),
    path("meal/<int:pk>/remove/", views.meal_delete, name="meal_delete"),
    path("meal/<int:pk>/served/", views.record_served, name="record_served"),
    path("week/copy/", views.copy_week, name="copy_week"),
]

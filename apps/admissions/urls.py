from django.urls import path

from . import views

app_name = "admissions"

urlpatterns = [
    path("application/", views.my_application, name="my_application"),
    path("application/apply/", views.apply, name="apply"),
    path("applications/", views.application_list, name="application_list"),
    path(
        "applications/<int:pk>/",
        views.application_detail,
        name="application_detail",
    ),
    path(
        "applications/<int:pk>/decide/",
        views.application_decide,
        name="application_decide",
    ),
    path(
        "applications/<int:pk>/allocate/",
        views.application_allocate,
        name="application_allocate",
    ),
    path("applications/allocate-all/", views.allocate_all, name="allocate_all"),
    path("rooms/", views.room_list, name="room_list"),
    path("residents/", views.resident_list, name="resident_list"),
    path("residents/<int:pk>/", views.resident_detail, name="resident_detail"),
    # Hostel vacating (HMS-F-062)
    path("vacating/", views.my_vacating, name="my_vacating"),
    path("vacating/submit/", views.submit_vacating, name="submit_vacating"),
    path("vacating/requests/", views.vacating_list, name="vacating_list"),
    path(
        "vacating/requests/<int:pk>/",
        views.vacating_detail,
        name="vacating_detail",
    ),
    path(
        "vacating/requests/<int:pk>/clearance/",
        views.vacating_clearance,
        name="vacating_clearance",
    ),
    path(
        "vacating/requests/<int:pk>/damage/",
        views.vacating_damage,
        name="vacating_damage",
    ),
    path(
        "vacating/requests/<int:pk>/approve/",
        views.vacating_approve,
        name="vacating_approve",
    ),
    path(
        "vacating/requests/<int:pk>/complete/",
        views.vacating_complete,
        name="vacating_complete",
    ),
]

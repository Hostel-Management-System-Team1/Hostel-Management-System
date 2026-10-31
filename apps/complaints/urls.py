from django.urls import path

from . import views

app_name = "complaints"

urlpatterns = [
    path("submit/", views.submit_complaint, name="submit_complaint"),
    path("my/", views.my_complaints, name="my_complaints"),
    path("manage/", views.manage_complaints, name="manage_complaints"),
    path(
        "assign/<int:complaint_id>/",
        views.assign_complaint,
        name="assign_complaint",
    ),
    path(
        "update/<int:complaint_id>/",
        views.update_complaint_status,
        name="update_complaint_status",
    ),
    path(
        "confirm/<int:complaint_id>/",
        views.confirm_resolution,
        name="confirm_resolution",
    ),
]
from django.urls import path

from . import views

app_name = "admissions"

urlpatterns = [
    path("application/", views.my_application, name="my_application"),
    path("application/apply/", views.apply, name="apply"),
    path("applications/", views.application_list, name="application_list"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("applications/<int:pk>/decide/", views.application_decide, name="application_decide"),
]

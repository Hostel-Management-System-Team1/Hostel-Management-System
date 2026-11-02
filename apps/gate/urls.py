
from django.urls import path

from . import views

app_name = "gate"

urlpatterns = [
    path("log/", views.gate_log, name="log"),
    path("outpasses/", views.outpass_page, name="outpasses"),
    path("warden/outpasses/", views.warden_outpass_page, name="warden_outpasses"),
    path("attendance/", views.attendance_page, name="attendance"),
    path("returns/", views.gate_returns_page, name="returns"),
]

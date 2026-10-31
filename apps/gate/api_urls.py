
from django.urls import path

from . import api

urlpatterns = [
    path(
        "gate/movements/manual",
        api.ManualGateMovementView.as_view(),
        name="api-gate-manual-movement",
    ),
    path(
        "gate/movements/device",
        api.GateDeviceEventView.as_view(),
        name="api-gate-device-event",
    ),
    path(
        "gate/curfew-alerts",
        api.CurfewAlertListView.as_view(),
        name="api-gate-curfew-alerts",
    ),
    path(
        "outpasses",
        api.OutpassListCreateView.as_view(),
        name="api-outpass-list-create",
    ),
    path(
        "outpasses/<int:pk>/decision",
        api.OutpassDecisionView.as_view(),
        name="api-outpass-decision",
    ),
    path(
        "outpasses/<int:pk>/return",
        api.OutpassReturnView.as_view(),
        name="api-outpass-return",
    ),
    path(
        "attendance",
        api.NightAttendanceView.as_view(),
        name="api-night-attendance",
    ),
]

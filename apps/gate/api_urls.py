
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
]

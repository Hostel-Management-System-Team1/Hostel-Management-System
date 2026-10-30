
import secrets

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotFound,
    ValidationError,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import roles

from . import services
from .models import CurfewAlert
from .serializers import (
    CurfewAlertSerializer,
    DeviceGateEventSerializer,
    ManualGateMovementSerializer,
)


class GateDeviceServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Gate device authentication is not configured."


class ManualGateMovementView(APIView):
    """POST /api/v1/gate/movements/manual."""

    permission_classes = [roles(User.Role.SECURITY_GUARD)]

    def post(self, request):
        serializer = ManualGateMovementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        resident = User.objects.filter(
            pk=data["resident_id"],
            role=User.Role.RESIDENT,
        ).first()

        if resident is None:
            raise NotFound("Resident not found.")

        try:
            movement = services.record_movement(
                resident=resident,
                direction=data["direction"],
                capture_method="MANUAL",
                occurred_at=data.get("occurred_at"),
                recorded_by=request.user,
            )
        except services.InvalidGateMovement as error:
            raise ValidationError(str(error)) from error

        return Response(
            {
                "movementId": movement.pk,
                "residentId": movement.resident_id,
                "direction": movement.direction,
                "captureMethod": movement.capture_method,
                "occurredAt": movement.occurred_at,
            },
            status=status.HTTP_201_CREATED,
        )


class GateDeviceEventView(APIView):
    """POST /api/v1/gate/movements/device.

    Authenticated through the X-Gate-Device-Key header.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        return "GateDevice"

    def post(self, request):
        configured_key = settings.GATE_DEVICE_API_KEY

        if not configured_key:
            raise GateDeviceServiceUnavailable()

        supplied_key = request.headers.get("X-Gate-Device-Key", "")

        if not secrets.compare_digest(supplied_key, configured_key):
            raise AuthenticationFailed("Invalid gate device credentials.")

        serializer = DeviceGateEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        resident = User.objects.filter(
            pk=data["resident_id"],
            role=User.Role.RESIDENT,
        ).first()

        if resident is None:
            raise NotFound("Resident not found.")

        try:
            movement = services.record_movement(
                resident=resident,
                direction=data["direction"],
                capture_method=data["capture_method"],
                occurred_at=data["occurred_at"],
                external_event_id=data["external_event_id"],
            )
        except services.InvalidGateMovement as error:
            raise ValidationError(str(error)) from error

        return Response(
            {
                "movementId": movement.pk,
                "residentId": movement.resident_id,
                "direction": movement.direction,
                "captureMethod": movement.capture_method,
                "occurredAt": movement.occurred_at,
            },
            status=status.HTTP_201_CREATED,
        )




class CurfewAlertListView(APIView):
    """GET /api/v1/gate/curfew-alerts."""

    permission_classes = [roles(User.Role.WARDEN)]

    def get(self, request):
        alerts = CurfewAlert.objects.select_related(
            "resident", "block"
        ).order_by("-detected_at")

        serializer = CurfewAlertSerializer(alerts, many=True)
        return Response(serializer.data)

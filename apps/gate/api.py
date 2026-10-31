
import secrets

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotFound,
    ValidationError,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import roles

from . import services
from .models import CurfewAlert, NightAttendance, OutpassRequest
from .serializers import (
    AttendanceGenerationSerializer,
    CurfewAlertSerializer,
    DeviceGateEventSerializer,
    ManualGateMovementSerializer,
    NightAttendanceSerializer,
    OutpassDecisionSerializer,
    OutpassRequestSerializer,
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



class OutpassListCreateView(APIView):
    """GET/POST /api/v1/outpasses."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in (
            User.Role.RESIDENT,
            User.Role.WARDEN,
        ):
            return Response(
                {"detail": "You do not have permission to view outpasses."},
                status=status.HTTP_403_FORBIDDEN,
            )

        outpasses = OutpassRequest.objects.select_related(
            "resident",
            "allocation__bed__room",
            "decided_by",
        )

        if request.user.role == User.Role.RESIDENT:
            outpasses = outpasses.filter(resident=request.user)

        serializer = OutpassRequestSerializer(outpasses, many=True)
        return Response(serializer.data)

    def post(self, request):
        if request.user.role != User.Role.RESIDENT:
            return Response(
                {"detail": "Only residents can submit outpass requests."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OutpassRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            outpass = services.submit_outpass(
                resident=request.user,
                destination=serializer.validated_data["destination"],
                contact_number=serializer.validated_data["contact_number"],
                expected_return_at=serializer.validated_data[
                    "expected_return_at"
                ],
            )
        except services.OutpassError as error:
            raise ValidationError(str(error)) from error

        return Response(
            OutpassRequestSerializer(outpass).data,
            status=status.HTTP_201_CREATED,
        )


class OutpassDecisionView(APIView):
    """PATCH /api/v1/outpasses/{id}/decision."""

    permission_classes = [roles(User.Role.WARDEN)]

    def patch(self, request, pk):
        serializer = OutpassDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            outpass = services.decide_outpass(
                outpass_id=pk,
                warden=request.user,
                decision=serializer.validated_data["decision"],
                reason=serializer.validated_data.get("reason", ""),
            )
        except OutpassRequest.DoesNotExist as error:
            raise NotFound("Outpass request not found.") from error
        except services.OutpassError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(OutpassRequestSerializer(outpass).data)


class OutpassReturnView(APIView):
    """POST /api/v1/outpasses/{id}/return."""

    permission_classes = [
        roles(User.Role.SECURITY_GUARD, User.Role.WARDEN)
    ]

    def post(self, request, pk):
        try:
            outpass = services.record_outpass_return(
                outpass_id=pk,
                guard=request.user,
            )
        except OutpassRequest.DoesNotExist as error:
            raise NotFound("Outpass request not found.") from error
        except services.OutpassError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(OutpassRequestSerializer(outpass).data)


class NightAttendanceView(APIView):
    """GET/POST /api/v1/attendance."""

    permission_classes = [roles(User.Role.WARDEN)]

    def get(self, request):
        attendance_date = request.query_params.get(
            "date",
            timezone.localdate().isoformat(),
        )

        records = NightAttendance.objects.select_related(
            "resident",
            "room__block",
        ).filter(attendance_date=attendance_date)

        block_id = request.query_params.get("block")
        if block_id:
            records = records.filter(room__block_id=block_id)

        serializer = NightAttendanceSerializer(records, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = AttendanceGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = services.generate_night_attendance(
            serializer.validated_data["attendance_date"]
        )

        return Response(result, status=status.HTTP_200_OK)


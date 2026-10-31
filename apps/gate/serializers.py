
from django.utils import timezone
from rest_framework import serializers

from .models import (
    CurfewAlert,
    GateMovement,
    NightAttendance,
    OutpassRequest,
)


class OutpassRequestSerializer(serializers.ModelSerializer):
    resident_name = serializers.SerializerMethodField()
    room = serializers.CharField(
        source="allocation.bed.room.number",
        read_only=True,
    )

    class Meta:
        model = OutpassRequest
        fields = [
            "id",
            "resident",
            "resident_name",
            "room",
            "destination",
            "contact_number",
            "expected_return_at",
            "status",
            "requested_at",
            "decided_by",
            "decided_at",
            "decision_reason",
            "returned_at",
        ]
        read_only_fields = [
            "id",
            "resident",
            "resident_name",
            "room",
            "status",
            "requested_at",
            "decided_by",
            "decided_at",
            "decision_reason",
            "returned_at",
        ]

    def get_resident_name(self, obj):
        return obj.resident.get_full_name() or obj.resident.username

    def validate_expected_return_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                "Expected return time must be in the future."
            )
        return value


class OutpassDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(
        choices=[
            OutpassRequest.Status.APPROVED,
            OutpassRequest.Status.REJECTED,
        ]
    )
    reason = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
    )


class NightAttendanceSerializer(serializers.ModelSerializer):
    resident_name = serializers.SerializerMethodField()
    block_name = serializers.CharField(source="room.block.name", read_only=True)
    room_number = serializers.CharField(source="room.number", read_only=True)
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = NightAttendance
        fields = [
            "id",
            "resident",
            "resident_name",
            "block_name",
            "room",
            "room_number",
            "attendance_date",
            "status",
            "status_display",
            "recorded_at",
        ]
        read_only_fields = fields

    def get_resident_name(self, obj):
        return obj.resident.get_full_name() or obj.resident.username


class AttendanceGenerationSerializer(serializers.Serializer):
    attendance_date = serializers.DateField()



class ManualGateMovementSerializer(serializers.Serializer):
    """Request body for a security guard's manual gate entry."""

    resident_id = serializers.IntegerField()
    direction = serializers.ChoiceField(
        choices=GateMovement.Direction.choices
    )
    occurred_at = serializers.DateTimeField(required=False)


class DeviceGateEventSerializer(serializers.Serializer):
    """Request body for an RFID or biometric device event."""

    resident_id = serializers.IntegerField()
    direction = serializers.ChoiceField(
        choices=GateMovement.Direction.choices
    )
    capture_method = serializers.ChoiceField(
        choices=[
            GateMovement.CaptureMethod.RFID,
            GateMovement.CaptureMethod.BIOMETRIC,
        ]
    )
    occurred_at = serializers.DateTimeField()
    external_event_id = serializers.CharField(max_length=100)


class CurfewAlertSerializer(serializers.ModelSerializer):
    resident_name = serializers.SerializerMethodField()
    block_name = serializers.CharField(source="block.name", read_only=True)

    class Meta:
        model = CurfewAlert
        fields = [
            "id",
            "resident",
            "resident_name",
            "block_name",
            "curfew_date",
            "detected_at",
            "notified_at",
        ]
        read_only_fields = fields

    def get_resident_name(self, obj):
        return obj.resident.get_full_name() or obj.resident.username

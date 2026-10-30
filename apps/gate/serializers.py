
from rest_framework import serializers

from .models import CurfewAlert, GateMovement


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

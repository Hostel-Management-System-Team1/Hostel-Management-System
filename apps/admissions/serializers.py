"""REST shapes for admission (SAD 4.3). Field names are camelCase on the wire."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from . import services
from .models import Application, Block, Gender, RoomType


class PersonalDetails(serializers.Serializer):
    fullName = serializers.CharField(source="full_name")
    dateOfBirth = serializers.DateField(source="date_of_birth")
    gender = serializers.ChoiceField(choices=Gender.choices)
    phone = serializers.CharField()
    email = serializers.EmailField()
    address = serializers.CharField()


class AcademicDetails(serializers.Serializer):
    programme = serializers.CharField()
    yearOfStudy = serializers.IntegerField(source="year_of_study")
    cgpa = serializers.DecimalField(max_digits=4, decimal_places=2)


class GuardianDetails(serializers.Serializer):
    name = serializers.CharField(source="guardian_name")
    relation = serializers.CharField(source="guardian_relation")
    phone = serializers.CharField(source="guardian_phone")
    email = serializers.EmailField(source="guardian_email", required=False, allow_blank=True)


class MedicalDetails(serializers.Serializer):
    bloodGroup = serializers.ChoiceField(
        source="blood_group", choices=Application.BloodGroup.choices, required=False,
        allow_blank=True,
    )
    conditions = serializers.CharField(
        source="medical_conditions", required=False, allow_blank=True
    )


class ApplicationSubmitSerializer(serializers.Serializer):
    """POST /api/v1/applications request body."""

    enrolmentNumber = serializers.CharField(source="enrolment_number")
    personalDetails = PersonalDetails()
    academicDetails = AcademicDetails()
    guardianDetails = GuardianDetails()
    medicalDetails = MedicalDetails(required=False)
    preferredBlock = serializers.SlugRelatedField(
        source="preferred_block", slug_field="name", queryset=Block.objects.all(),
        required=False, allow_null=True,
    )
    roomType = serializers.ChoiceField(source="room_type", choices=RoomType.choices)

    def flat(self):
        """The validated data as the flat keyword arguments the service takes."""
        data = dict(self.validated_data)
        for key in ("personalDetails", "academicDetails", "guardianDetails", "medicalDetails"):
            data.update(data.pop(key, {}))
        return data

    def save(self, applicant):
        try:
            return services.submit_application(applicant, **self.flat())
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error

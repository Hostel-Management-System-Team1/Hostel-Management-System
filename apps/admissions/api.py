from rest_framework import status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import roles

from . import allocation as allocator
from . import services
from .models import Application
from .serializers import AllocationRequestSerializer, ApplicationSubmitSerializer


class DuplicateApplicationError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "An application already exists for this enrolment number and session."


class ApplicationCreateView(APIView):
    """POST /api/v1/applications — submit an admission application (HMS-F-001)."""

    permission_classes = [roles(User.Role.RESIDENT)]

    def post(self, request):
        serializer = ApplicationSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = serializer.save(request.user)
        except services.DuplicateApplication as error:
            raise DuplicateApplicationError(str(error)) from error
        return Response(
            {"applicationNumber": application.application_number, "status": "Submitted"},
            status=status.HTTP_201_CREATED,
        )


class NoVacantBedError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "No vacant bed matches the applicant's gender, block and room type."


class AllocationCreateView(APIView):
    """POST /api/v1/allocations — allocate a bed to an approved application (HMS-F-002)."""

    permission_classes = [roles(User.Role.WARDEN, User.Role.ADMINISTRATOR)]

    def post(self, request):
        serializer = AllocationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = Application.objects.filter(
            application_number=serializer.validated_data["applicationNumber"],
            status=Application.Status.APPROVED,
        ).first()
        if application is None:
            raise NotFound("Application not found or not approved.")
        try:
            allocation = allocator.allocate(application, request.user)
        except allocator.NoVacantBed as error:
            raise NoVacantBedError(str(error)) from error
        bed = allocation.bed
        return Response(
            {
                "bedId": bed.pk,
                "block": bed.room.block.name,
                "room": bed.room.number,
                "allocatedAt": allocation.allocated_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

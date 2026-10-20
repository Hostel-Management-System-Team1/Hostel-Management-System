from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import roles

from . import services
from .serializers import ApplicationSubmitSerializer


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

from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User
from .permissions import roles
from .serializers import UserSerializer


class MeView(APIView):
    """GET /api/v1/me — who the caller is."""

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserListView(ListAPIView):
    """GET /api/v1/users — account list, Hostel Administrators only (HMS-SR-002)."""

    permission_classes = [roles(User.Role.ADMINISTRATOR)]
    serializer_class = UserSerializer
    queryset = User.objects.order_by("username")

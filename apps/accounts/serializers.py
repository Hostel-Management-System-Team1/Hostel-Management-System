from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Account details for the API. Never includes the password hash."""

    name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "name", "email", "role", "is_active", "last_login")
        read_only_fields = fields

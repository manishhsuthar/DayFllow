from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from accounts.models import CustomUser
from accounts.permissions import is_owner
from accounts.utils import create_employee_with_login_id, generate_temp_password


class LoginSerializer(serializers.Serializer):
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        login_input = (data.get("login_id") or "").strip()

        # Accept an email address as well as a login id.
        if "@" in login_input:
            match = CustomUser.objects.filter(email__iexact=login_input).first()
            if match:
                login_input = match.login_id

        user = authenticate(username=login_input, password=data["password"])
        if not user:
            # One message for every failure mode, so the endpoint cannot be used to
            # tell "no such account" apart from "wrong password".
            raise serializers.ValidationError("Invalid login credentials")
        if not user.is_active:
            raise serializers.ValidationError("Invalid login credentials")

        data["user"] = user
        return data


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value, user=self.context.get("user"))
        return value

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "The new password must differ from the current one."}
            )
        return attrs


class CreateEmployeeSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=50)
    last_name = serializers.CharField(max_length=50)
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[("EMP", "Employee"), ("INT", "Intern"), ("HR", "HR")])
    date_of_joining = serializers.DateField()
    department = serializers.CharField(max_length=100, required=False, allow_blank=True)
    employment_type = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_role(self, value):
        actor = self.context["request"].user

        # Only the organization owner may mint another management account.
        if value == "HR" and not is_owner(actor):
            raise serializers.ValidationError("Only an administrator can create HR accounts.")

        organization = actor.organization
        if organization and organization.roles and value not in organization.roles:
            raise serializers.ValidationError("Role is not allowed by company configuration.")
        return value

    def validate_department(self, value):
        value = (value or "").strip()
        organization = self.context["request"].user.organization
        if value and organization and organization.departments:
            known = {d.lower() for d in organization.departments}
            if value.lower() not in known:
                raise serializers.ValidationError(
                    "Department is not configured for this organization."
                )
        return value

    def validate_date_of_joining(self, value):
        from django.utils import timezone

        if value > timezone.now().date().replace(year=timezone.now().year + 2):
            raise serializers.ValidationError("Joining date is unreasonably far in the future.")
        return value

    @transaction.atomic
    def create(self, validated_data):
        from django.contrib.auth.hashers import make_password

        actor = self.context["request"].user
        organization = actor.organization

        role = validated_data["role"]
        employment_type = "" if role == "HR" else validated_data.get("employment_type", "")

        temp_password = generate_temp_password()
        user = create_employee_with_login_id(
            organization,
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=role,
            date_of_joining=validated_data["date_of_joining"],
            department=validated_data.get("department", ""),
            employment_type=employment_type,
            password=make_password(temp_password),
            must_change_password=True,
        )
        return user, temp_password

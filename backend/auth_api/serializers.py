from django.contrib.auth import authenticate
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from accounts.models import CustomUser
from accounts.utils import generate_login_id, generate_temp_password
from accounts.company_table_service import insert_company_user_row
from django.contrib.auth.hashers import make_password
from django.db import transaction
from accounts.models import CompanyConfig

class LoginSerializer(serializers.Serializer):
    login_id = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        login_input = data.get("login_id")
        if login_input and "@" in login_input:
            user_by_email = CustomUser.objects.filter(email=login_input).first()
            if user_by_email:
                data["login_id"] = user_by_email.login_id

        user = authenticate(
            username=data["login_id"],
            password=data["password"]
        )

        if not user:
            raise serializers.ValidationError("Invalid login credentials")

        if not user.is_active:
            raise serializers.ValidationError("Account is inactive")

        data["user"] = user
        return data

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
    
class CreateEmployeeSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=[("EMP", "Employee"), ("INT", "Intern"), ("HR", "HR")])
    date_of_joining = serializers.DateField()
    department = serializers.CharField(required=False, allow_blank=True)
    employment_type = serializers.CharField(required=False, allow_blank=True)
    salary = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)

    def validate_email(self, value):
        if CustomUser.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_role(self, value):
        request = self.context.get("request")
        creator_role = getattr(getattr(request, "user", None), "role", None)
        if creator_role == "HR" and value == "HR":
            raise serializers.ValidationError("HR users cannot create HR accounts.")

        company_name = getattr(getattr(request, "user", None), "company_name", "")
        if company_name:
            config = CompanyConfig.objects.filter(company_name=company_name).first()
            if config and config.roles:
                if value not in config.roles:
                    raise serializers.ValidationError("Role is not allowed by company configuration.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        company_name = getattr(getattr(request, "user", None), "company_name", "")
        role = validated_data["role"]
        employment_type = validated_data.get("employment_type", "")
        if role == "HR":
            employment_type = ""

        with transaction.atomic():
            login_id = generate_login_id(
                validated_data["first_name"],
                validated_data["last_name"],
                validated_data["date_of_joining"],
            )

            temp_password = generate_temp_password()

            user = CustomUser.objects.create(
                login_id=login_id,
                email=validated_data["email"],
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                company_name=company_name,
                role=role,
                date_of_joining=validated_data["date_of_joining"],
                department=validated_data.get("department", ""),
                employment_type=employment_type,
                salary=validated_data.get("salary"),
                password=make_password(temp_password),
                must_change_password=True,
            )

            insert_company_user_row(
                company_name=company_name,
                user=user,
                created_by_user_id=getattr(getattr(request, "user", None), "id", None),
            )

        return user, temp_password

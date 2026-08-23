from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from accounts.models import CustomUser
from .models import EmployeeSalary, PayrollRecord


class SalaryUpsertSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    monthly_salary = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.00"))
    currency = serializers.CharField(required=False, allow_blank=False, default="INR")

    def validate_employee_id(self, value):
        request = self.context["request"]
        employee = CustomUser.objects.filter(
            id=value, organization=request.user.organization_id
        ).first()
        if not employee:
            raise serializers.ValidationError("Employee not found for your company.")
        if employee.role == "ADMIN":
            raise serializers.ValidationError("Salary cannot be assigned to admin accounts.")
        self.context["employee"] = employee
        return value

    def validate_currency(self, value):
        normalized = value.upper().strip()
        if not normalized:
            raise serializers.ValidationError("Currency is required.")
        return normalized


class EmployeeSalarySerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(source="employee.id", read_only=True)
    employee_login_id = serializers.CharField(source="employee.login_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.CharField(source="employee.role", read_only=True)

    adjusted_salary = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeSalary
        fields = (
            "employee_id",
            "employee_login_id",
            "employee_name",
            "employee_role",
            "monthly_salary",
            "currency",
            "expense",
            "outstanding",
            "adjusted_salary",
            "updated_at",
        )

    def get_adjusted_salary(self, obj):
        return obj.monthly_salary - obj.outstanding


    def get_employee_name(self, obj):
        full_name = f"{obj.employee.first_name} {obj.employee.last_name}".strip()
        return full_name or obj.employee.login_id


class PayrollRunSerializer(serializers.Serializer):
    month = serializers.CharField(required=False)
    employee_id = serializers.IntegerField(required=False)
    force_recompute = serializers.BooleanField(required=False, default=False)

    def validate_month(self, value):
        try:
            parsed = datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise serializers.ValidationError("Month should be in YYYY-MM format.") from exc
        return parsed.date().replace(day=1)

    def validate_employee_id(self, value):
        request = self.context["request"]
        employee = CustomUser.objects.filter(
            id=value, organization=request.user.organization_id
        ).first()
        if not employee:
            raise serializers.ValidationError("Employee not found for your company.")
        if employee.role == "ADMIN":
            raise serializers.ValidationError("Payroll cannot be generated for admin accounts.")
        return value

    def validate(self, attrs):
        attrs.setdefault("month", date.today().replace(day=1))
        return attrs


class PayrollRecordSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(source="employee.id", read_only=True)
    employee_login_id = serializers.CharField(source="employee.login_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.CharField(source="employee.role", read_only=True)
    month_label = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRecord
        fields = (
            "id",
            "employee_id",
            "employee_login_id",
            "employee_name",
            "employee_role",
            "month",
            "month_label",
            "status",
            "total_days_in_month",
            "attendance_entries",
            "present_days",
            "half_days",
            "leave_days",
            "absent_days",
            "payable_days",
            "designated_salary",
            "expense_amount",
            "net_salary",
            "created_at",
            "credited_at",
        )


    def get_employee_name(self, obj):
        full_name = f"{obj.employee.first_name} {obj.employee.last_name}".strip()
        return full_name or obj.employee.login_id

    def get_month_label(self, obj):
        return obj.month.strftime("%B %Y")


class PayrollSlipSerializer(serializers.ModelSerializer):
    employee = serializers.SerializerMethodField()
    company_name = serializers.CharField(source="employee.organization.name", read_only=True)
    company_logo_url = serializers.SerializerMethodField()
    month_label = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRecord
        fields = (
            "id",
            "company_name",
            "company_logo_url",
            "month",
            "month_label",
            "employee",
            "status",
            "total_days_in_month",
            "attendance_entries",
            "present_days",
            "half_days",
            "leave_days",
            "absent_days",
            "payable_days",
            "designated_salary",
            "expense_amount",
            "net_salary",
            "created_at",
            "credited_at",
        )


    def get_employee(self, obj):
        full_name = f"{obj.employee.first_name} {obj.employee.last_name}".strip()
        return {
            "id": obj.employee.id,
            "login_id": obj.employee.login_id,
            "name": full_name or obj.employee.login_id,
            "email": obj.employee.email,
            "department": obj.employee.department,
            "employment_type": obj.employee.employment_type,
            "role": obj.employee.role,
        }

    def get_company_logo_url(self, obj):
        organization = obj.employee.organization
        return organization.logo_url if organization else ""

    def get_month_label(self, obj):
        return obj.month.strftime("%B %Y")


def quantize_currency(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

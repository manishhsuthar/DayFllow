from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from accounts.models import CustomUser
from .models import EmployeeSalary, ExpenseClaim, PayrollRecord


#: The platform bills and pays in USD. Other codes are rejected rather than stored
#: unconverted, which is how INR amounts ended up labelled as though comparable.
SUPPORTED_CURRENCIES = ("USD",)


class SalaryUpsertSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    monthly_salary = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("10000000.00"),
    )
    currency = serializers.CharField(required=False, allow_blank=False, default="USD")

    def validate_employee_id(self, value):
        request = self.context["request"]
        employee = CustomUser.objects.filter(
            id=value, organization=request.user.organization_id, is_active=True
        ).first()
        if not employee:
            raise serializers.ValidationError("Employee not found for your company.")
        if employee.role == "ADMIN":
            raise serializers.ValidationError("Salary cannot be assigned to admin accounts.")
        self.context["employee"] = employee
        return value

    def validate_currency(self, value):
        normalized = (value or "").upper().strip()
        if normalized not in SUPPORTED_CURRENCIES:
            raise serializers.ValidationError(
                f"Currency must be one of: {', '.join(SUPPORTED_CURRENCIES)}."
            )
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
        organization = getattr(self.context["request"].user, "organization", None)
        current_month = (organization.today() if organization else date.today()).replace(day=1)
        attrs.setdefault("month", current_month)
        # Payroll cannot be run for a month that has not started.
        if attrs["month"] > current_month:
            raise serializers.ValidationError(
                {"month": "Payroll cannot be generated for a future month."}
            )
        return attrs


class PayrollRecordSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(source="employee.id", read_only=True)
    employee_login_id = serializers.CharField(source="employee.login_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    employee_role = serializers.CharField(source="employee.role", read_only=True)
    month_label = serializers.SerializerMethodField()
    currency = serializers.CharField(source="salary.currency", read_only=True)

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
            "gross_salary",
            "expense_amount",
            "expense_carried_forward",
            "net_salary",
            "currency",
            "revision",
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
            "gross_salary",
            "expense_amount",
            "expense_carried_forward",
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


class ExpenseClaimSerializer(serializers.ModelSerializer):
    employee_login_id = serializers.CharField(source="employee.login_id", read_only=True)
    employee_name = serializers.SerializerMethodField()
    reviewed_by_login_id = serializers.CharField(
        source="reviewed_by.login_id", read_only=True, default=None
    )

    class Meta:
        model = ExpenseClaim
        fields = (
            "id",
            "employee",
            "employee_login_id",
            "employee_name",
            "amount",
            "description",
            "incurred_on",
            "status",
            "review_note",
            "reviewed_by_login_id",
            "reviewed_at",
            "created_at",
        )
        read_only_fields = fields

    def get_employee_name(self, obj):
        return obj.employee.full_name


class ExpenseClaimSubmitSerializer(serializers.Serializer):
    """Submitting a claim. Only review moves money (audit V-07)."""

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        max_value=Decimal("1000000.00"),
    )
    description = serializers.CharField(max_length=255)
    incurred_on = serializers.DateField()
    employee_id = serializers.IntegerField(required=False)

    def validate_description(self, value):
        value = (value or "").strip()
        if len(value) < 3:
            raise serializers.ValidationError("Please describe the expense.")
        return value

    def validate_incurred_on(self, value):
        from django.utils import timezone

        today = timezone.localdate()
        if value > today:
            raise serializers.ValidationError("An expense cannot be incurred in the future.")
        if value < today - timedelta(days=365):
            raise serializers.ValidationError("Expenses must be claimed within a year.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        actor = request.user
        employee_id = attrs.get("employee_id")

        if employee_id and employee_id != actor.id:
            from accounts.permissions import can_manage_target

            employee = CustomUser.objects.filter(
                id=employee_id, organization=actor.organization_id, is_active=True
            ).first()
            if not employee:
                raise serializers.ValidationError({"employee_id": "Employee not found."})
            if not can_manage_target(actor, employee):
                raise serializers.ValidationError(
                    {"employee_id": "You cannot file expenses for this employee."}
                )
        else:
            employee = actor

        self.context["employee"] = employee
        return attrs

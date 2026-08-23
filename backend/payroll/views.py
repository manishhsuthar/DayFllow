import calendar
from datetime import date, datetime
from decimal import Decimal

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from attendance.models import Attendance
from organizations.scoping import organization_of
from .models import EmployeeSalary, PayrollRecord
from .serializers import (
    EmployeeSalarySerializer,
    PayrollRecordSerializer,
    PayrollRunSerializer,
    PayrollSlipSerializer,
    SalaryUpsertSerializer,
    quantize_currency,
)


def _is_payroll_manager(user):
    return user.role in ["ADMIN", "HR"]


def _parse_query_month(month_raw):
    if not month_raw:
        today = date.today()
        return today.replace(day=1)
    return datetime.strptime(month_raw, "%Y-%m").date().replace(day=1)


def _attendance_month_stats(employee, payroll_month):
    records = Attendance.objects.filter(
        user=employee,
        date__year=payroll_month.year,
        date__month=payroll_month.month,
    )
    counts = records.aggregate(
        attendance_entries=Count("id"),
        present_days=Count("id", filter=Q(status="PRESENT")),
        half_days=Count("id", filter=Q(status="HALF_DAY")),
        leave_days=Count("id", filter=Q(status="LEAVE")),
        absent_days=Count("id", filter=Q(status="ABSENT")),
    )
    return {
        "attendance_entries": counts.get("attendance_entries") or 0,
        "present_days": counts.get("present_days") or 0,
        "half_days": counts.get("half_days") or 0,
        "leave_days": counts.get("leave_days") or 0,
        "absent_days": counts.get("absent_days") or 0,
    }


def _compute_payroll_for_employee(employee, salary, payroll_month):
    days_in_month = calendar.monthrange(payroll_month.year, payroll_month.month)[1]
    
    organization = employee.organization
    if organization and organization.bypass_attendance:
        attendance = {
            "attendance_entries": days_in_month,
            "present_days": days_in_month,
            "half_days": 0,
            "leave_days": 0,
            "absent_days": 0,
        }
    else:
        attendance = _attendance_month_stats(employee, payroll_month)
        
    payable_days = Decimal(attendance["present_days"]) + (Decimal(attendance["half_days"]) * Decimal("0.5"))

    daily_rate = Decimal(salary.monthly_salary) / Decimal(days_in_month)
    base_net_salary = daily_rate * payable_days

    expense_to_pay = Decimal(salary.outstanding)
    net_salary = quantize_currency(base_net_salary - expense_to_pay)

    return {
        "month": payroll_month,
        "total_days_in_month": days_in_month,
        "attendance_entries": attendance["attendance_entries"],
        "present_days": attendance["present_days"],
        "half_days": attendance["half_days"],
        "leave_days": attendance["leave_days"],
        "absent_days": attendance["absent_days"],
        "payable_days": quantize_currency(payable_days),
        "designated_salary": quantize_currency(Decimal(salary.monthly_salary)),
        "expense_amount": expense_to_pay,
        "net_salary": net_salary,
    }



def _get_accessible_payroll(user, payroll_id):
    queryset = PayrollRecord.objects.select_related("employee", "salary")
    if _is_payroll_manager(user):
        return queryset.filter(
            id=payroll_id,
            employee__organization=organization_of(user),
        ).first()
    return queryset.filter(id=payroll_id, employee=user).first()


class EmployeeSalaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _is_payroll_manager(request.user):
            salaries = EmployeeSalary.objects.filter(
                employee__organization=organization_of(request.user)
            ).select_related("employee")
            return Response(EmployeeSalarySerializer(salaries, many=True).data)

        salary = EmployeeSalary.objects.filter(employee=request.user).select_related("employee").first()
        if not salary:
            return Response({"detail": "Salary is not configured yet."}, status=status.HTTP_404_NOT_FOUND)
        return Response(EmployeeSalarySerializer(salary).data)

    def post(self, request):
        if not _is_payroll_manager(request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = SalaryUpsertSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        employee = serializer.context["employee"]
        with transaction.atomic():
            salary, created = EmployeeSalary.objects.get_or_create(
                employee=employee,
                defaults={
                    "monthly_salary": serializer.validated_data["monthly_salary"],
                    "currency": serializer.validated_data["currency"],
                    "set_by": request.user,
                    "updated_by": request.user,
                },
            )
            if not created:
                salary.monthly_salary = serializer.validated_data["monthly_salary"]
                salary.currency = serializer.validated_data["currency"]
                salary.updated_by = request.user
                salary.save(update_fields=["monthly_salary", "currency", "updated_by", "updated_at"])

        return Response(
            {
                "message": "Salary saved successfully.",
                "salary": EmployeeSalarySerializer(salary).data,
            },
            status=status.HTTP_200_OK,
        )


class PayrollRunAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_payroll_manager(request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        serializer = PayrollRunSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        payroll_month = serializer.validated_data["month"]
        employee_id = serializer.validated_data.get("employee_id")
        force_recompute = serializer.validated_data.get("force_recompute", False)

        salaries = EmployeeSalary.objects.filter(
            employee__organization=organization_of(request.user)
        ).select_related("employee")
        if employee_id:
            salaries = salaries.filter(employee_id=employee_id)

        if not salaries.exists():
            return Response(
                {"detail": "No salary configurations found for selected employees."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output = []
        with transaction.atomic():
            for salary in salaries:
                computed = _compute_payroll_for_employee(salary.employee, salary, payroll_month)
                payroll, created = PayrollRecord.objects.get_or_create(
                    employee=salary.employee,
                    month=payroll_month,
                    defaults={
                        **computed,
                        "salary": salary,
                        "status": "PENDING",
                        "generated_by": request.user,
                    },
                )

                if not created:
                    if payroll.status == "PAID":
                        payroll.status = "PENDING"
                        payroll.credited_at = None
                        payroll.credited_by = None

                    payroll.salary = salary
                    payroll.total_days_in_month = computed["total_days_in_month"]
                    payroll.attendance_entries = computed["attendance_entries"]
                    payroll.present_days = computed["present_days"]
                    payroll.half_days = computed["half_days"]
                    payroll.leave_days = computed["leave_days"]
                    payroll.absent_days = computed["absent_days"]
                    payroll.payable_days = computed["payable_days"]
                    payroll.designated_salary = computed["designated_salary"]
                    payroll.expense_amount = computed["expense_amount"]
                    payroll.net_salary = computed["net_salary"]
                    payroll.generated_by = request.user
                    payroll.save()

                output.append(
                    {
                        "employee_id": salary.employee.id,
                        "employee_login_id": salary.employee.login_id,
                        "status": "generated" if created else "updated",
                        "net_salary": str(payroll.net_salary),
                    }
                )

        return Response(
            {
                "month": payroll_month.strftime("%Y-%m"),
                "results": output,
            },
            status=status.HTTP_200_OK,
        )


class PayrollListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        month_raw = request.query_params.get("month")
        status_filter = request.query_params.get("status")
        employee_id = request.query_params.get("employee_id")

        queryset = PayrollRecord.objects.select_related("employee", "salary")
        if _is_payroll_manager(request.user):
            queryset = queryset.filter(employee__organization=organization_of(request.user))
        else:
            queryset = queryset.filter(employee=request.user)

        if month_raw:
            try:
                month_date = _parse_query_month(month_raw)
            except ValueError:
                return Response(
                    {"detail": "Month should be in YYYY-MM format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(month=month_date)

        if status_filter:
            upper_status = status_filter.upper()
            if upper_status not in ["PENDING", "PAID"]:
                return Response(
                    {"detail": "Status can be either PENDING or PAID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=upper_status)

        if employee_id and _is_payroll_manager(request.user):
            queryset = queryset.filter(employee_id=employee_id)

        serializer = PayrollRecordSerializer(queryset.order_by("-month", "employee_id"), many=True)
        return Response(serializer.data)


class PayrollCreditAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, payroll_id):
        if not _is_payroll_manager(request.user):
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        payroll = PayrollRecord.objects.filter(
            id=payroll_id,
            employee__organization=organization_of(request.user),
        ).select_related("employee").first()
        if not payroll:
            return Response({"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND)

        if payroll.status == "PAID":
            return Response(
                {"detail": "Payroll is already marked as paid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            payroll.status = "PAID"
            payroll.credited_at = timezone.now()
            payroll.credited_by = request.user
            payroll.save(update_fields=["status", "credited_at", "credited_by", "updated_at"])

            salary = EmployeeSalary.objects.filter(employee=payroll.employee).first()
            if salary and payroll.expense_amount > 0:
                salary.outstanding = max(Decimal("0.00"), salary.outstanding - payroll.expense_amount)
                salary.save(update_fields=["outstanding", "updated_at"])

        return Response(
            {
                "message": "Salary credited successfully.",
                "payroll": PayrollRecordSerializer(payroll).data,
            },
            status=status.HTTP_200_OK,
        )



class PayrollSlipAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payroll_id):
        payroll = _get_accessible_payroll(request.user, payroll_id)

        if not payroll:
            return Response({"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PayrollSlipSerializer(payroll)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PayrollSlipHTMLAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payroll_id):
        payroll = _get_accessible_payroll(request.user, payroll_id)
        if not payroll:
            return Response(
                {"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND
            )

        organization = payroll.employee.organization
        html = render_to_string(
            "payroll/salary_slip.html",
            {
                "payroll": payroll,
                "organization": organization,
                "employee_name": payroll.employee.full_name,
                "month_label": payroll.month.strftime("%B %Y"),
                "currency_symbol": "$",
            },
        )
        response = HttpResponse(html)
        # The slip is served from the API origin and renders tenant-supplied data,
        # so it gets its own restrictive CSP on top of template autoescaping.
        response["Content-Security-Policy"] = (
            "default-src 'none'; img-src https: data:; style-src 'unsafe-inline'"
        )
        response["X-Content-Type-Options"] = "nosniff"
        if request.GET.get("download") == "true":
            filename = f"salary_slip_{payroll.employee.login_id}_{payroll.month:%Y-%m}.html"
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class AddExpenseAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        amount_str = request.data.get("amount")
        if not amount_str:
            return Response({"detail": "Amount is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = Decimal(str(amount_str))
            if amount <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({"detail": "Amount must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)

        employee_id = request.data.get("employee_id")
        from accounts.models import CustomUser
        if employee_id:
            if not _is_payroll_manager(request.user):
                return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
            employee = CustomUser.objects.filter(
                id=employee_id, organization=organization_of(request.user)
            ).first()
            if not employee:
                return Response({"detail": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            employee = request.user

        salary, created = EmployeeSalary.objects.get_or_create(
            employee=employee,
            defaults={
                "monthly_salary": Decimal("0.00"),
                "currency": "INR",
                "set_by": request.user,
                "updated_by": request.user,
            }
        )

        with transaction.atomic():
            salary.expense += amount
            salary.outstanding += amount
            salary.save(update_fields=["expense", "outstanding", "updated_at"])

        return Response(
            {
                "message": "Expense added successfully.",
                "salary": EmployeeSalarySerializer(salary).data,
            },
            status=status.HTTP_200_OK,
        )


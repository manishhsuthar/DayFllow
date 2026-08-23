"""Payroll.

Three defects shaped this rewrite:

* Nothing floored net pay, so `outstanding` expenses could drive a payslip
  negative -- the audit reproduced -49000.00 (V-08).
* Re-running payroll for a month silently reset already-credited payslips to
  PENDING and discarded `credited_at`/`credited_by`, so the operator saw an unpaid
  payslip and paid it twice (V-20).
* `force_recompute` was parsed and then never read (V-21).
"""

import calendar
import logging
from datetime import date, datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsManagement, IsOrganizationOwner, can_manage_target
from attendance.models import Attendance
from audit.models import AuditLog
from audit.services import diff, record
from core.pagination import DefaultPagination
from organizations.scoping import organization_of

from .models import EmployeeSalary, ExpenseClaim, PayrollRecord
from .serializers import (
    EmployeeSalarySerializer,
    ExpenseClaimSerializer,
    ExpenseClaimSubmitSerializer,
    PayrollRecordSerializer,
    PayrollRunSerializer,
    PayrollSlipSerializer,
    SalaryUpsertSerializer,
    quantize_currency,
)

logger = logging.getLogger("dayflow.audit")

#: Ceiling on how much of an outstanding balance may be recovered from one month's
#: pay, as a fraction of what was earned. The remainder carries forward.
MAX_DEDUCTION_FRACTION = Decimal("0.50")


def _is_payroll_manager(user):
    return getattr(user, "role", None) in ("ADMIN", "HR")


def _parse_query_month(month_raw):
    if not month_raw:
        return date.today().replace(day=1)
    return datetime.strptime(month_raw, "%Y-%m").date().replace(day=1)


def _attendance_month_stats(employee, payroll_month):
    counts = Attendance.objects.filter(
        user=employee,
        date__year=payroll_month.year,
        date__month=payroll_month.month,
    ).aggregate(
        attendance_entries=Count("id"),
        present_days=Count("id", filter=Q(status="PRESENT")),
        half_days=Count("id", filter=Q(status="HALF_DAY")),
        leave_days=Count("id", filter=Q(status="LEAVE")),
        absent_days=Count("id", filter=Q(status="ABSENT")),
    )
    return {key: counts.get(key) or 0 for key in counts}


def compute_payroll_for_employee(employee, salary, payroll_month):
    """Compute one payslip. Net pay is always >= 0."""
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

    payable_days = Decimal(attendance["present_days"]) + (
        Decimal(attendance["half_days"]) * Decimal("0.5")
    )
    daily_rate = Decimal(salary.monthly_salary) / Decimal(days_in_month)
    gross = quantize_currency(daily_rate * payable_days)

    # Recover expenses, but never more than half of what was earned, and never
    # more than is actually outstanding. Whatever is left carries forward instead
    # of pushing the payslip negative.
    outstanding = Decimal(salary.outstanding)
    recoverable = quantize_currency(gross * MAX_DEDUCTION_FRACTION)
    deduction = min(outstanding, recoverable)
    carried_forward = quantize_currency(outstanding - deduction)
    net = quantize_currency(gross - deduction)

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
        "gross_salary": gross,
        "expense_amount": deduction,
        "expense_carried_forward": carried_forward,
        "net_salary": net,
    }


def _get_accessible_payroll(user, payroll_id):
    queryset = PayrollRecord.objects.select_related(
        "employee", "employee__organization", "salary"
    )
    if _is_payroll_manager(user):
        return queryset.filter(
            id=payroll_id, employee__organization=organization_of(user)
        ).first()
    return queryset.filter(id=payroll_id, employee=user).first()


class EmployeeSalaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _is_payroll_manager(request.user):
            salaries = (
                EmployeeSalary.objects.filter(
                    employee__organization=organization_of(request.user)
                )
                .select_related("employee")
                .order_by("employee__login_id")
            )
            if not request.user.role == "ADMIN":
                salaries = salaries.exclude(employee__role="ADMIN")
            return Response(EmployeeSalarySerializer(salaries, many=True).data)

        salary = (
            EmployeeSalary.objects.filter(employee=request.user)
            .select_related("employee")
            .first()
        )
        if not salary:
            return Response(
                {"detail": "Salary is not configured yet."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(EmployeeSalarySerializer(salary).data)

    def post(self, request):
        """Set an employee's salary. Owner only, and always audited."""
        if not request.user.role == "ADMIN":
            return Response(
                {"detail": "Only an administrator can set salaries."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SalaryUpsertSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        employee = serializer.context["employee"]

        with transaction.atomic():
            salary, created = EmployeeSalary.objects.select_for_update().get_or_create(
                employee=employee,
                defaults={
                    "monthly_salary": serializer.validated_data["monthly_salary"],
                    "currency": serializer.validated_data["currency"],
                    "set_by": request.user,
                    "updated_by": request.user,
                },
            )
            before = {"monthly_salary": salary.monthly_salary, "currency": salary.currency}
            if not created:
                salary.monthly_salary = serializer.validated_data["monthly_salary"]
                salary.currency = serializer.validated_data["currency"]
                salary.updated_by = request.user
                salary.save(
                    update_fields=["monthly_salary", "currency", "updated_by", "updated_at"]
                )
            after = {"monthly_salary": salary.monthly_salary, "currency": salary.currency}

            record(
                organization=employee.organization,
                actor=request.user,
                action=AuditLog.Action.SALARY_SET,
                target=employee,
                label=employee.login_id,
                changes=diff({} if created else before, after) or {"created": True, **after},
            )

        return Response(
            {"message": "Salary saved successfully.", "salary": EmployeeSalarySerializer(salary).data},
            status=status.HTTP_200_OK,
        )


class PayrollRunAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManagement]

    def post(self, request):
        serializer = PayrollRunSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        organization = organization_of(request.user)
        payroll_month = serializer.validated_data["month"]
        employee_id = serializer.validated_data.get("employee_id")
        force_recompute = serializer.validated_data.get("force_recompute", False)

        salaries = EmployeeSalary.objects.filter(
            employee__organization=organization, employee__is_active=True
        ).select_related("employee", "employee__organization")
        if employee_id:
            salaries = salaries.filter(employee_id=employee_id)

        if not salaries.exists():
            return Response(
                {"detail": "No salary configurations found for selected employees."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        results, skipped = [], []
        with transaction.atomic():
            for salary in salaries:
                computed = compute_payroll_for_employee(
                    salary.employee, salary, payroll_month
                )
                payroll = (
                    PayrollRecord.objects.select_for_update()
                    .filter(employee=salary.employee, month=payroll_month)
                    .first()
                )

                if payroll is None:
                    payroll = PayrollRecord.objects.create(
                        employee=salary.employee,
                        salary=salary,
                        status="PENDING",
                        generated_by=request.user,
                        **computed,
                    )
                    results.append(self._row(salary.employee, payroll, "generated"))
                    continue

                # A credited payslip is a financial record of money that moved.
                # Recomputing it used to silently reset it to PENDING and drop
                # credited_at/credited_by, so it looked unpaid and got paid twice.
                if payroll.status == "PAID":
                    skipped.append(
                        {
                            "employee_id": salary.employee.id,
                            "employee_login_id": salary.employee.login_id,
                            "reason": "already_paid",
                            "credited_at": payroll.credited_at,
                        }
                    )
                    continue

                if not force_recompute:
                    skipped.append(
                        {
                            "employee_id": salary.employee.id,
                            "employee_login_id": salary.employee.login_id,
                            "reason": "already_generated",
                            "hint": "Pass force_recompute=true to recompute pending payslips.",
                        }
                    )
                    continue

                for field, value in computed.items():
                    setattr(payroll, field, value)
                payroll.salary = salary
                payroll.generated_by = request.user
                payroll.revision += 1
                payroll.save()
                results.append(self._row(salary.employee, payroll, "recomputed"))

            record(
                organization=organization,
                actor=request.user,
                action=AuditLog.Action.PAYROLL_RUN,
                label=f"Payroll {payroll_month:%Y-%m}",
                changes={
                    "month": payroll_month,
                    "generated": len([r for r in results if r["status"] == "generated"]),
                    "recomputed": len([r for r in results if r["status"] == "recomputed"]),
                    "skipped": len(skipped),
                    "force_recompute": force_recompute,
                },
            )

        return Response(
            {"month": payroll_month.strftime("%Y-%m"), "results": results, "skipped": skipped},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _row(employee, payroll, outcome):
        return {
            "employee_id": employee.id,
            "employee_login_id": employee.login_id,
            "status": outcome,
            "net_salary": str(payroll.net_salary),
            "expense_carried_forward": str(payroll.expense_carried_forward),
            "revision": payroll.revision,
        }


class PayrollListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = PayrollRecord.objects.select_related("employee", "salary")
        if _is_payroll_manager(request.user):
            queryset = queryset.filter(employee__organization=organization_of(request.user))
            if request.user.role != "ADMIN":
                queryset = queryset.exclude(employee__role="ADMIN")
        else:
            queryset = queryset.filter(employee=request.user)

        month_raw = request.query_params.get("month")
        if month_raw:
            try:
                queryset = queryset.filter(month=_parse_query_month(month_raw))
            except ValueError:
                return Response(
                    {"detail": "Month should be in YYYY-MM format."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        status_filter = request.query_params.get("status")
        if status_filter:
            upper = status_filter.upper()
            if upper not in ("PENDING", "PAID"):
                return Response(
                    {"detail": "Status can be either PENDING or PAID."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=upper)

        employee_id = request.query_params.get("employee_id")
        if employee_id and _is_payroll_manager(request.user):
            queryset = queryset.filter(employee_id=employee_id)

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(
            queryset.order_by("-month", "employee_id"), request, view=self
        )
        return paginator.get_paginated_response(PayrollRecordSerializer(page, many=True).data)


class PayrollCreditAPIView(APIView):
    """Mark a payslip as paid. Owner only -- this is money leaving the business."""

    permission_classes = [IsAuthenticated, IsOrganizationOwner]

    def post(self, request, payroll_id):
        organization = organization_of(request.user)

        with transaction.atomic():
            payroll = (
                PayrollRecord.objects.select_for_update()
                .filter(id=payroll_id, employee__organization=organization)
                .select_related("employee")
                .first()
            )
            if not payroll:
                return Response(
                    {"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND
                )
            if payroll.status == "PAID":
                return Response(
                    {"detail": "Payroll is already marked as paid."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payroll.status = "PAID"
            payroll.credited_at = timezone.now()
            payroll.credited_by = request.user
            payroll.save(
                update_fields=["status", "credited_at", "credited_by", "updated_at"]
            )

            salary = (
                EmployeeSalary.objects.select_for_update()
                .filter(employee=payroll.employee)
                .first()
            )
            if salary and payroll.expense_amount > 0:
                salary.outstanding = max(
                    Decimal("0.00"), salary.outstanding - payroll.expense_amount
                )
                salary.save(update_fields=["outstanding", "updated_at"])

            record(
                organization=organization,
                actor=request.user,
                action=AuditLog.Action.PAYROLL_CREDITED,
                target=payroll,
                label=f"{payroll.employee.login_id} {payroll.month:%Y-%m}",
                changes={
                    "net_salary": payroll.net_salary,
                    "expense_recovered": payroll.expense_amount,
                    "month": payroll.month,
                },
            )

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
            return Response(
                {"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND
            )
        return Response(PayrollSlipSerializer(payroll).data, status=status.HTTP_200_OK)


class PayrollSlipHTMLAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payroll_id):
        payroll = _get_accessible_payroll(request.user, payroll_id)
        if not payroll:
            return Response(
                {"detail": "Payroll record not found."}, status=status.HTTP_404_NOT_FOUND
            )

        html = render_to_string(
            "payroll/salary_slip.html",
            {
                "payroll": payroll,
                "organization": payroll.employee.organization,
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


class ExpenseClaimListCreateAPIView(APIView):
    """Submit an expense claim, or list the ones you may see.

    Submitting no longer moves money. The old endpoint wrote straight into
    `EmployeeSalary.outstanding` and only checked for a manager when an
    `employee_id` was supplied, so any employee could omit it and post an
    unlimited, unreviewable, irreversible amount against their own pay (V-07).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if _is_payroll_manager(request.user):
            queryset = ExpenseClaim.objects.filter(
                employee__organization=organization_of(request.user)
            ).select_related("employee")
            employee_id = request.query_params.get("employee_id")
            if employee_id:
                queryset = queryset.filter(employee_id=employee_id)
        else:
            queryset = ExpenseClaim.objects.filter(employee=request.user).select_related(
                "employee"
            )

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter.upper())

        paginator = DefaultPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ExpenseClaimSerializer(page, many=True).data)

    def post(self, request):
        serializer = ExpenseClaimSubmitSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        employee = serializer.context["employee"]

        with transaction.atomic():
            claim = ExpenseClaim.objects.create(
                employee=employee,
                amount=serializer.validated_data["amount"],
                description=serializer.validated_data["description"],
                incurred_on=serializer.validated_data["incurred_on"],
                submitted_by=request.user,
            )
            record(
                organization=employee.organization,
                actor=request.user,
                action=AuditLog.Action.EXPENSE_SUBMITTED,
                target=claim,
                label=f"{employee.login_id} {claim.amount}",
                changes={"amount": claim.amount, "description": claim.description},
            )

        return Response(ExpenseClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class ExpenseClaimReviewAPIView(APIView):
    """Approve or reject a claim. Approval is the only thing that moves money."""

    permission_classes = [IsAuthenticated, IsManagement]

    def post(self, request, claim_id):
        action = (request.data.get("action") or "").upper()
        if action not in ("APPROVE", "REJECT"):
            return Response(
                {"detail": "Action must be APPROVE or REJECT."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        organization = organization_of(request.user)
        note = (request.data.get("note") or "")[:255]

        with transaction.atomic():
            claim = (
                ExpenseClaim.objects.select_for_update()
                .filter(id=claim_id, employee__organization=organization)
                .select_related("employee")
                .first()
            )
            if not claim:
                return Response(
                    {"detail": "Expense claim not found."}, status=status.HTTP_404_NOT_FOUND
                )
            if not can_manage_target(request.user, claim.employee):
                return Response(
                    {"detail": "You do not have permission to review this claim."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if claim.employee_id == request.user.id:
                return Response(
                    {"detail": "You cannot review your own expense claim."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if claim.status != ExpenseClaim.Status.PENDING:
                return Response(
                    {"detail": f"This claim was already {claim.status.lower()}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            claim.status = (
                ExpenseClaim.Status.APPROVED
                if action == "APPROVE"
                else ExpenseClaim.Status.REJECTED
            )
            claim.reviewed_by = request.user
            claim.reviewed_at = timezone.now()
            claim.review_note = note
            claim.save(
                update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"]
            )

            if claim.status == ExpenseClaim.Status.APPROVED:
                salary, _ = EmployeeSalary.objects.select_for_update().get_or_create(
                    employee=claim.employee,
                    defaults={
                        "monthly_salary": Decimal("0.00"),
                        "currency": "USD",
                        "set_by": request.user,
                        "updated_by": request.user,
                    },
                )
                salary.expense += claim.amount
                salary.outstanding += claim.amount
                salary.save(update_fields=["expense", "outstanding", "updated_at"])

            record(
                organization=organization,
                actor=request.user,
                action=(
                    AuditLog.Action.EXPENSE_APPROVED
                    if claim.status == ExpenseClaim.Status.APPROVED
                    else AuditLog.Action.EXPENSE_REJECTED
                ),
                target=claim,
                label=f"{claim.employee.login_id} {claim.amount}",
                changes={"amount": claim.amount, "note": note},
            )

        return Response(ExpenseClaimSerializer(claim).data, status=status.HTTP_200_OK)

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import CustomUser


class EmployeeSalary(models.Model):
    employee = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="salary_details",
    )
    monthly_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    # The platform bills and pays in USD.
    currency = models.CharField(max_length=3, default="USD")
    #: Lifetime total of approved expense claims.
    expense = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    #: Approved but not yet recovered from pay.
    outstanding = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salaries_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salaries_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("employee_id",)

    def __str__(self):
        return f"{self.employee.login_id} - {self.monthly_salary} {self.currency}"


class PayrollRecord(models.Model):
    STATUS_CHOICES = (
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
    )

    employee = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="payroll_records",
    )
    salary = models.ForeignKey(
        EmployeeSalary,
        on_delete=models.PROTECT,
        related_name="payroll_records",
    )
    month = models.DateField(
        help_text="First day of payroll month (YYYY-MM-01).",
        db_index=True,
    )

    total_days_in_month = models.PositiveSmallIntegerField()
    attendance_entries = models.PositiveSmallIntegerField(default=0)
    present_days = models.PositiveSmallIntegerField(default=0)
    half_days = models.PositiveSmallIntegerField(default=0)
    leave_days = models.PositiveSmallIntegerField(default=0)
    absent_days = models.PositiveSmallIntegerField(default=0)
    payable_days = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))

    designated_salary = models.DecimalField(max_digits=12, decimal_places=2)
    gross_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Earned before expense recovery.",
    )
    #: Amount actually recovered this period. Capped, so net pay never goes negative.
    expense_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    #: Outstanding balance left to recover in later periods.
    expense_carried_forward = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    net_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    revision = models.PositiveSmallIntegerField(default=1)


    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="PENDING")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payrolls_generated",
    )
    credited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payrolls_credited",
    )
    credited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-month", "employee_id")
        constraints = [
            models.UniqueConstraint(
                fields=("employee", "month"),
                name="unique_employee_month_payroll",
            ),
            # Net pay is clamped at zero in code; the database refuses to store a
            # negative either way (audit V-08).
            models.CheckConstraint(
                condition=models.Q(net_salary__gte=Decimal("0.00")),
                name="payroll_net_salary_non_negative",
            ),
        ]

    def __str__(self):
        return f"{self.employee.login_id} - {self.month:%Y-%m} - {self.status}"



class ExpenseClaim(models.Model):
    """An employee expense, submitted for approval.

    Expenses used to be written straight into `EmployeeSalary.outstanding` by
    `POST /api/payroll/salaries/add-expense/`, which only checked for a payroll
    manager when an `employee_id` was supplied -- so any employee could omit it and
    move an unlimited, unreviewable, irreversible amount against their own pay
    (audit V-07). Claims now carry a state machine, and only approval moves money.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    employee = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="expense_claims"
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    description = models.CharField(max_length=255)
    incurred_on = models.DateField()

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims_submitted",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expense_claims_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["employee", "status"])]

    def __str__(self):
        return f"{self.employee.login_id} {self.amount} {self.status}"

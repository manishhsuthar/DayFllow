"""Append-only audit trail.

Salary changes, payroll runs, salary credits, leave approvals, employee
deactivation and configuration changes previously left no trace of who did what
(audit V-30). `PayrollRecord` carried `generated_by`/`credited_by`, but re-running
payroll nulled them out, so even that record was destructible.

Entries are written inside the transaction that performs the action, so an audit
entry exists if and only if the action committed. Nothing in the application ever
updates or deletes one.
"""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        SALARY_SET = "SALARY_SET", "Salary set"
        EXPENSE_SUBMITTED = "EXPENSE_SUBMITTED", "Expense submitted"
        EXPENSE_APPROVED = "EXPENSE_APPROVED", "Expense approved"
        EXPENSE_REJECTED = "EXPENSE_REJECTED", "Expense rejected"
        PAYROLL_RUN = "PAYROLL_RUN", "Payroll run"
        PAYROLL_CREDITED = "PAYROLL_CREDITED", "Payroll credited"
        LEAVE_APPROVED = "LEAVE_APPROVED", "Leave approved"
        LEAVE_REJECTED = "LEAVE_REJECTED", "Leave rejected"
        EMPLOYEE_CREATED = "EMPLOYEE_CREATED", "Employee created"
        EMPLOYEE_DEACTIVATED = "EMPLOYEE_DEACTIVATED", "Employee deactivated"
        EMPLOYEE_REACTIVATED = "EMPLOYEE_REACTIVATED", "Employee reactivated"
        SETTINGS_CHANGED = "SETTINGS_CHANGED", "Organization settings changed"
        SUBSCRIPTION_CHANGED = "SUBSCRIPTION_CHANGED", "Subscription changed"

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="audit_entries",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
        help_text="Null for system-initiated actions such as Stripe webhooks.",
    )
    actor_label = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Actor's login id captured at write time, so the entry survives deletion.",
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)

    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    target_label = models.CharField(max_length=255, blank=True, default="")

    #: What changed, as {"field": {"from": ..., "to": ...}}, plus any context.
    changes = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["organization", "-created_at"]),
            models.Index(fields=["organization", "action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} by {self.actor_label or 'system'}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise RuntimeError("Audit entries are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Audit entries are append-only and cannot be deleted.")

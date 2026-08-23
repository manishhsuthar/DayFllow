from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.models import CustomUser
from organizations.models import Organization
from attendance.models import Attendance
from leave.models import LeaveRequest
from payroll.models import EmployeeSalary, PayrollRecord
from .notifications import broadcast_data_change


WATCHED_MODELS = (
    CustomUser,
    Organization,
    Attendance,
    LeaveRequest,
    EmployeeSalary,
    PayrollRecord,
)


@receiver(post_save, dispatch_uid="realtime.broadcast_model_save")
def broadcast_model_save(sender, instance, created, **kwargs):
    if sender not in WATCHED_MODELS:
        return
    broadcast_data_change(instance, "created" if created else "updated")


@receiver(post_delete, dispatch_uid="realtime.broadcast_model_delete")
def broadcast_model_delete(sender, instance, **kwargs):
    if sender not in WATCHED_MODELS:
        return
    broadcast_data_change(instance, "deleted")

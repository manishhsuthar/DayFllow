from django.contrib import admin

from .models import EmployeeSalary, PayrollRecord


@admin.register(EmployeeSalary)
class EmployeeSalaryAdmin(admin.ModelAdmin):
    list_display = ("employee", "monthly_salary", "currency", "updated_at")
    search_fields = ("employee__login_id", "employee__email", "employee__organization__name")
    list_filter = ("currency",)


@admin.register(PayrollRecord)
class PayrollRecordAdmin(admin.ModelAdmin):
    list_display = ("employee", "month", "status", "designated_salary", "net_salary", "credited_at")
    search_fields = ("employee__login_id", "employee__email", "employee__organization__name")
    list_filter = ("status", "month")


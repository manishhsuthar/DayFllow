"""Move `CustomUser.salary` into payroll before the column is dropped.

`CustomUser.salary` and `payroll.EmployeeSalary.monthly_salary` recorded the same
fact in two places, and nothing kept them in step -- the employee directory
reported one number while payroll paid the other (audit V-08, V-18).
EmployeeSalary is the surviving source of truth, so any value that exists only on
the user is copied across first.

Existing EmployeeSalary rows win: they are what payroll has actually been paying.
"""

from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    CustomUser = apps.get_model("accounts", "CustomUser")
    EmployeeSalary = apps.get_model("payroll", "EmployeeSalary")

    already_configured = set(EmployeeSalary.objects.values_list("employee_id", flat=True))

    new_rows = [
        EmployeeSalary(
            employee_id=user.id,
            monthly_salary=user.salary,
            currency="USD",
            expense=Decimal("0.00"),
            outstanding=Decimal("0.00"),
        )
        for user in CustomUser.objects.exclude(salary=None).exclude(role="ADMIN")
        if user.id not in already_configured
    ]
    if new_rows:
        EmployeeSalary.objects.bulk_create(new_rows)


def backwards(apps, schema_editor):
    # The column is re-added empty by the reverse of 0014; repopulate it.
    CustomUser = apps.get_model("accounts", "CustomUser")
    EmployeeSalary = apps.get_model("payroll", "EmployeeSalary")
    for salary in EmployeeSalary.objects.all():
        CustomUser.objects.filter(pk=salary.employee_id).update(salary=salary.monthly_salary)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_backfill_organizations"),
        ("payroll", "0002_employeesalary_expense_employeesalary_outstanding_and_more"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]

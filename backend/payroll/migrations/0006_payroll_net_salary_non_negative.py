"""Forbid negative net pay at the database level (audit V-08)."""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0005_clamp_negative_net_salary"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='payrollrecord',
            constraint=models.CheckConstraint(condition=models.Q(('net_salary__gte', Decimal('0.00'))), name='payroll_net_salary_non_negative'),
        ),
    ]

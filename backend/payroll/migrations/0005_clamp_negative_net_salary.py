"""Clamp historical negative net salaries before the CHECK constraint lands.

Nothing floored the net-pay calculation, so `outstanding` expenses could drive a
payslip below zero -- the audit reproduced a net salary of -49000.00 (V-08).
0004 adds a database constraint forbidding that, so any existing negative row has
to be corrected first.

The shortfall is not written off: it moves into `expense_carried_forward` so it is
still recoverable from later periods, which is what should have happened all along.

Currency is deliberately left untouched. Existing rows may be denominated in INR,
and relabelling them USD would silently change what every historical payslip says
was paid. New records default to USD; converting the old ones is a business
decision, not a migration.
"""

from decimal import Decimal

from django.db import migrations


def forwards(apps, schema_editor):
    PayrollRecord = apps.get_model("payroll", "PayrollRecord")

    for record in PayrollRecord.objects.filter(net_salary__lt=Decimal("0.00")):
        shortfall = -record.net_salary
        record.expense_carried_forward = shortfall
        # Only the part actually covered by this period's pay was ever recoverable.
        record.expense_amount = max(Decimal("0.00"), record.expense_amount - shortfall)
        record.net_salary = Decimal("0.00")
        record.save(
            update_fields=["net_salary", "expense_amount", "expense_carried_forward"]
        )


def backwards(apps, schema_editor):
    # Clamping is not reversible: the original negative value is not recoverable
    # from the clamped row, and re-introducing one would violate 0004's constraint.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("payroll", "0004_expense_claims_and_non_negative_pay"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]

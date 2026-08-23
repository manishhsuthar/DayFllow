from datetime import date
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import CustomUser
from attendance.models import Attendance
from organizations.models import Organization
from payroll.models import EmployeeSalary, PayrollRecord


class PayrollFlowTests(APITestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Acme", slug="acme")
        self.admin = CustomUser.objects.create_user(
            email="admin@example.com",
            password="adminpass123",
            login_id="admin-login",
            organization=self.organization,
            role="ADMIN",
        )
        self.organization.owner = self.admin
        self.organization.save(update_fields=["owner"])
        self.employee = CustomUser.objects.create_user(
            email="employee@example.com",
            password="emppass123",
            login_id="emp-login",
            organization=self.organization,
            role="EMP",
        )

    def test_payroll_run_is_based_on_attendance_and_can_be_credited(self):
        self.client.force_authenticate(user=self.admin)

        salary_response = self.client.post(
            reverse("payroll-salaries"),
            {
                "employee_id": self.employee.id,
                "monthly_salary": "30000.00",
                "currency": "USD",
            },
            format="json",
        )
        self.assertEqual(salary_response.status_code, status.HTTP_200_OK)

        Attendance.objects.create(user=self.employee, date=date(2026, 2, 1), status="PRESENT")
        Attendance.objects.create(user=self.employee, date=date(2026, 2, 2), status="PRESENT")
        Attendance.objects.create(user=self.employee, date=date(2026, 2, 3), status="HALF_DAY")

        run_response = self.client.post(
            reverse("payroll-run"),
            {"month": "2026-02", "employee_id": self.employee.id},
            format="json",
        )
        self.assertEqual(run_response.status_code, status.HTTP_200_OK)

        payroll = PayrollRecord.objects.get(employee=self.employee, month=date(2026, 2, 1))
        self.assertEqual(payroll.status, "PENDING")
        self.assertEqual(payroll.present_days, 2)
        self.assertEqual(payroll.half_days, 1)
        self.assertEqual(payroll.payable_days, Decimal("2.50"))
        self.assertEqual(payroll.net_salary, Decimal("2678.57"))
        self.assertEqual(payroll.expense_amount, Decimal("0.00"))

        credit_response = self.client.post(
            reverse("payroll-credit", kwargs={"payroll_id": payroll.id}),
            {},
            format="json",
        )
        self.assertEqual(credit_response.status_code, status.HTTP_200_OK)

        payroll.refresh_from_db()
        self.assertEqual(payroll.status, "PAID")
        self.assertIsNotNone(payroll.credited_at)

    def test_employee_notifications_include_salary_credit(self):
        salary = EmployeeSalary.objects.create(
            employee=self.employee,
            monthly_salary=Decimal("20000.00"),
            currency="USD",
            set_by=self.admin,
            updated_by=self.admin,
        )
        payroll = PayrollRecord.objects.create(
            employee=self.employee,
            salary=salary,
            month=date(2026, 2, 1),
            total_days_in_month=28,
            attendance_entries=2,
            present_days=2,
            half_days=0,
            leave_days=0,
            absent_days=0,
            payable_days=Decimal("2.00"),
            designated_salary=Decimal("20000.00"),
            net_salary=Decimal("1428.57"),
            status="PAID",
            credited_by=self.admin,
            credited_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.employee)
        response = self.client.get("/api/dashboard/notifications/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            any(item["id"] == f"salary-{payroll.id}" for item in response.data["items"])
        )

    def test_expense_claim_requires_approval_before_it_affects_pay(self):
        salary = EmployeeSalary.objects.create(
            employee=self.employee,
            monthly_salary=Decimal("30000.00"),
            currency="USD",
            set_by=self.admin,
            updated_by=self.admin,
        )

        # The employee submits. Nothing moves yet: submitting used to write
        # straight into `outstanding` with no review at all (audit V-07).
        self.client.force_authenticate(user=self.employee)
        response = self.client.post(
            reverse("payroll-expenses"),
            {
                "amount": "5000.00",
                "description": "Travel to client site",
                "incurred_on": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        claim_id = response.data["id"]

        salary.refresh_from_db()
        self.assertEqual(salary.expense, Decimal("0.00"))
        self.assertEqual(salary.outstanding, Decimal("0.00"))

        # The admin approves, and only now does the balance change.
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("payroll-expense-review", kwargs={"claim_id": claim_id}),
            {"action": "APPROVE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        salary.refresh_from_db()
        self.assertEqual(salary.expense, Decimal("5000.00"))
        self.assertEqual(salary.outstanding, Decimal("5000.00"))

    def test_outstanding_expenses_never_push_a_payslip_negative(self):
        salary = EmployeeSalary.objects.create(
            employee=self.employee,
            monthly_salary=Decimal("30000.00"),
            currency="USD",
            outstanding=Decimal("6200.50"),
            set_by=self.admin,
            updated_by=self.admin,
        )

        # One present day out of 28 earns ~1071.43, far less than is outstanding.
        Attendance.objects.create(user=self.employee, date=date(2026, 2, 1), status="PRESENT")

        self.client.force_authenticate(user=self.admin)
        run_response = self.client.post(
            reverse("payroll-run"),
            {"month": "2026-02", "employee_id": self.employee.id},
            format="json",
        )
        self.assertEqual(run_response.status_code, status.HTTP_200_OK, run_response.data)

        payroll = PayrollRecord.objects.get(employee=self.employee, month=date(2026, 2, 1))
        self.assertEqual(payroll.gross_salary, Decimal("1071.43"))
        # Recovery is capped at half of gross; the rest waits for a later period.
        self.assertEqual(payroll.expense_amount, Decimal("535.72"))
        self.assertEqual(payroll.net_salary, Decimal("535.71"))
        self.assertEqual(payroll.expense_carried_forward, Decimal("5664.78"))
        self.assertGreaterEqual(payroll.net_salary, Decimal("0.00"))

        credit_response = self.client.post(
            reverse("payroll-credit", kwargs={"payroll_id": payroll.id}),
            {},
            format="json",
        )
        self.assertEqual(credit_response.status_code, status.HTTP_200_OK)
        salary.refresh_from_db()
        self.assertEqual(salary.outstanding, Decimal("5664.78"))

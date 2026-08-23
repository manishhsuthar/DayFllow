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

    def test_add_expense_and_payroll_adjustment(self):
        salary = EmployeeSalary.objects.create(
            employee=self.employee,
            monthly_salary=Decimal("30000.00"),
            currency="USD",
            set_by=self.admin,
            updated_by=self.admin,
        )

        self.client.force_authenticate(user=self.employee)
        response = self.client.post(
            reverse("payroll-add-expense"),
            {"amount": "5000.00"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        salary.refresh_from_db()
        self.assertEqual(salary.expense, Decimal("5000.00"))
        self.assertEqual(salary.outstanding, Decimal("5000.00"))

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            reverse("payroll-add-expense"),
            {"amount": "1200.50", "employee_id": self.employee.id},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        salary.refresh_from_db()
        self.assertEqual(salary.expense, Decimal("6200.50"))
        self.assertEqual(salary.outstanding, Decimal("6200.50"))

        Attendance.objects.create(user=self.employee, date=date(2026, 2, 1), status="PRESENT")
        run_response = self.client.post(
            reverse("payroll-run"),
            {"month": "2026-02", "employee_id": self.employee.id},
            format="json",
        )
        self.assertEqual(run_response.status_code, status.HTTP_200_OK)

        payroll = PayrollRecord.objects.get(employee=self.employee, month=date(2026, 2, 1))
        self.assertEqual(payroll.expense_amount, Decimal("6200.50"))
        self.assertEqual(payroll.net_salary, Decimal("-5129.07"))

        credit_response = self.client.post(
            reverse("payroll-credit", kwargs={"payroll_id": payroll.id}),
            {},
            format="json",
        )
        self.assertEqual(credit_response.status_code, status.HTTP_200_OK)
        salary.refresh_from_db()
        self.assertEqual(salary.outstanding, Decimal("0.00"))


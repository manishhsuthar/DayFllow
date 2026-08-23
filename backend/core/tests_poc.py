"""Proof-of-vulnerability suite for the pre-hardening DayFlow codebase.

Each test demonstrates a concrete, exploitable defect against the API as it
exists today. They are expected to PASS while the defect is present; the
matching fix commit flips each one into a regression test.
"""
from datetime import date, timedelta
from decimal import Decimal

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import CustomUser, CompanyConfig
from attendance.models import Attendance
from leave.models import LeaveRequest
from payroll.models import EmployeeSalary, PayrollRecord


def mk_user(login_id, company, role="EMP", **kw):
    u = CustomUser.objects.create(
        login_id=login_id,
        email=f"{login_id}@{company.replace(' ', '').lower()}.com",
        company_name=company,
        role=role,
        **kw,
    )
    u.set_password("Str0ngPassw0rd!42")
    u.save()
    return u


def auth(user):
    from rest_framework_simplejwt.tokens import RefreshToken
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return c


class V01TenantTakeover(TestCase):
    """V-01: public registration lets anyone become ADMIN of an existing company.

    The Postgres-only company-table side effect is stubbed out so this exercises the
    authorization defect rather than V-13 (see below).
    """

    @patch("accounts.views.insert_company_user_row", lambda **kw: None)
    @patch("accounts.views.ensure_company_table", lambda name: "company_stub")
    def test_attacker_registers_into_victim_company_and_reads_payroll(self):
        victim_admin = mk_user("VICTIMADMIN", "Acme Corp", role="ADMIN")
        victim_emp = mk_user("VICTIMEMP", "Acme Corp", role="EMP")
        EmployeeSalary.objects.create(
            employee=victim_emp, monthly_salary=Decimal("9000.00"), currency="INR"
        )

        # Attacker signs up, unauthenticated, claiming the victim's company name.
        resp = APIClient().post(
            "/api/accounts/register/",
            {
                "email": "attacker@evil.test",
                "password": "Str0ngPassw0rd!42",
                "first_name": "Mal",
                "last_name": "Lory",
                "company_name": "Acme Corp",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        attacker = CustomUser.objects.filter(email="attacker@evil.test").first()
        self.assertIsNotNone(attacker)
        self.assertEqual(attacker.role, "ADMIN")
        self.assertEqual(attacker.company_name, "Acme Corp")

        # ...and can now read every employee and salary in the victim's tenant.
        c = auth(attacker)
        emps = c.get("/api/accounts/employees/")
        self.assertEqual(emps.status_code, 200)
        logins = {e["login_id"] for e in emps.data["results"]}
        self.assertIn("VICTIMEMP", logins)
        self.assertIn("VICTIMADMIN", logins)

        sal = c.get("/api/payroll/salaries/")
        self.assertEqual(sal.status_code, 200)
        self.assertEqual(str(sal.data[0]["monthly_salary"]), "9000.00")


class V02RegistrationLeaksTraceback(TestCase):
    """V-02 FIXED: internal errors return an opaque reference, never a traceback."""

    @patch("accounts.views.ensure_company_table", side_effect=RuntimeError("db exploded"))
    def test_traceback_is_not_disclosed(self, _stub):
        with self.assertLogs("django.request", level="ERROR"):
            resp = APIClient().post(
                "/api/accounts/register/",
                {
                    "email": "trace@evil.test",
                    "password": "Str0ngPassw0rd!42",
                    "first_name": "T",
                    "last_name": "B",
                    "company_name": "Trace Co",
                },
                format="json",
            )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn("traceback", resp.data)
        body = str(resp.data)
        self.assertNotIn('File "', body)
        self.assertNotIn("db exploded", body)
        self.assertNotIn("site-packages", body)
        # A correlation id is returned so the operator can find the real error in logs.
        self.assertRegex(resp.data["error_id"], r"^[0-9a-f]{12}$")


@override_settings(DEBUG=True)
class V03LoginBackdoor(TestCase):
    """V-03 FIXED: the hardcoded credentials are gone, even with DEBUG on."""

    def test_hardcoded_credentials_are_rejected(self):
        resp = APIClient().post(
            "/api/auth/login/",
            {"login_id": "admin1@gmail.com", "password": "adminisadmin"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertNotIn("access", resp.data)
        # And crucially: no account was conjured into existence by the attempt.
        self.assertFalse(CustomUser.objects.filter(email="admin1@gmail.com").exists())

    def test_no_backdoor_string_remains_in_source(self):
        import inspect
        from auth_api import serializers as auth_serializers

        src = inspect.getsource(auth_serializers)
        self.assertNotIn("adminisadmin", src)
        self.assertNotIn("admin1@gmail.com", src)
        self.assertNotIn("create_superuser", src)


class V04CheckoutCrash(TestCase):
    """V-04: check-out on an attendance row with no check_in raises TypeError (500)."""

    def test_checkout_without_checkin_is_unhandled(self):
        emp = mk_user("CRASHEMP", "Acme Corp")
        # Approved-leave flow creates an Attendance row with check_in=None.
        Attendance.objects.create(user=emp, date=date.today(), status="LEAVE")
        c = auth(emp)
        c.raise_request_exception = False
        with self.assertLogs("django.request", level="ERROR"):
            resp = c.post("/api/attendance/check-out/", {}, format="json")
        self.assertEqual(resp.status_code, 500)


class V05LeaveDateValidation(TestCase):
    """V-05: leave accepts end_date before start_date and unbounded ranges."""

    def test_reversed_range_accepted(self):
        emp = mk_user("BADDATES", "Acme Corp")
        c = auth(emp)
        resp = c.post(
            "/api/leave/apply/",
            {
                "leave_type": "CASUAL",
                "start_date": "2030-12-31",
                "end_date": "2030-01-01",
                "reason": "reversed",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)

    def test_decade_long_leave_accepted(self):
        emp = mk_user("LONGLEAVE", "Acme Corp")
        c = auth(emp)
        resp = c.post(
            "/api/leave/apply/",
            {
                "leave_type": "PAID",
                "start_date": "2030-01-01",
                "end_date": "2040-01-01",
                "reason": "decade off",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)


class V06LeaveApprovalDestroysAttendance(TestCase):
    """V-06: approving leave overwrites existing PRESENT attendance, erasing worked days."""

    def test_approval_overwrites_present_day(self):
        admin = mk_user("OVERADMIN", "Acme Corp", role="ADMIN")
        emp = mk_user("OVEREMP", "Acme Corp")
        worked = date.today() - timedelta(days=1)
        Attendance.objects.create(
            user=emp, date=worked, status="PRESENT", total_hours=9.0
        )
        lv = LeaveRequest.objects.create(
            user=emp, leave_type="SICK", start_date=worked, end_date=worked, reason="x"
        )
        auth(admin).post(f"/api/leave/action/{lv.id}/", {"action": "APPROVE"}, format="json")
        att = Attendance.objects.get(user=emp, date=worked)
        self.assertEqual(att.status, "LEAVE")          # worked day destroyed
        self.assertEqual(att.total_hours, 9.0)         # stale hours left behind


class V07EmployeeSelfExpense(TestCase):
    """V-07: any employee can post expenses against their own salary with no approval."""

    def test_employee_inflates_own_outstanding(self):
        emp = mk_user("SELFEXP", "Acme Corp")
        EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("5000.00"), currency="INR"
        )
        c = auth(emp)
        resp = c.post("/api/payroll/salaries/add-expense/", {"amount": "999999.00"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        s = EmployeeSalary.objects.get(employee=emp)
        self.assertEqual(s.outstanding, Decimal("999999.00"))


class V08NegativeNetSalary(TestCase):
    """V-08: outstanding expenses can drive a payroll run to a negative net salary."""

    def test_payroll_goes_negative(self):
        admin = mk_user("NEGADMIN", "Acme Corp", role="ADMIN")
        emp = mk_user("NEGEMP", "Acme Corp")
        CompanyConfig.objects.create(company_name="Acme Corp", bypass_attendance=True)
        EmployeeSalary.objects.create(
            employee=emp,
            monthly_salary=Decimal("1000.00"),
            currency="INR",
            outstanding=Decimal("50000.00"),
        )
        month = date.today().replace(day=1).strftime("%Y-%m")
        resp = auth(admin).post("/api/payroll/run/", {"month": month}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        rec = PayrollRecord.objects.get(employee=emp)
        self.assertLess(rec.net_salary, Decimal("0.00"))
        print("\n[V-08] net salary computed as:", rec.net_salary)


class V09SlipXSS(TestCase):
    """V-09: the HTML salary slip interpolates tenant-controlled data unescaped."""

    def test_company_name_is_injected_raw(self):
        payload = '"><script>alert(document.domain)</script>'
        admin = mk_user("XSSADMIN", payload, role="ADMIN")
        emp = mk_user("XSSEMP", payload)
        sal = EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("100.00"), currency="INR"
        )
        rec = PayrollRecord.objects.create(
            employee=emp, salary=sal, month=date.today().replace(day=1),
            total_days_in_month=30, designated_salary=Decimal("100.00"),
            net_salary=Decimal("100.00"),
        )
        resp = auth(admin).get(f"/api/payroll/slips/{rec.id}/html/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"<script>alert(document.domain)</script>", resp.content)


class V10PaymentGrantsNothing(TestCase):
    """V-10: payment verification stores no subscription -- paying grants no entitlement."""

    def test_verify_endpoint_persists_nothing(self):
        import hashlib
        import hmac

        from django.conf import settings

        order_id, payment_id = "order_TEST123", "pay_TEST123"
        sig = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        resp = APIClient().post(
            "/api/accounts/payments/razorpay/verify/",
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": sig,
            },
            format="json",
        )
        # Unauthenticated caller, valid-looking signature, 200 OK, zero side effects.
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["message"], "Payment verified successfully.")
        from django.apps import apps
        names = {m.__name__ for m in apps.get_models()}
        self.assertNotIn("Subscription", names)
        self.assertNotIn("Plan", names)


class V11LoginIdCollision(TestCase):
    """V-11: login_id generator collides across tenants -- employee creation hard-fails."""

    def test_counter_is_global_and_racy(self):
        from accounts.utils import generate_login_id
        joining = date(2030, 1, 10)

        # Tenant A hires someone.
        a = generate_login_id("John", "Doe", joining)
        CustomUser.objects.create(
            login_id=a, email="a@a.test", company_name="A Co", date_of_joining=joining
        )

        # Tenant B hires an unrelated person. The serial jumped -- the id leaks how many
        # employees exist platform-wide, across every tenant.
        b = generate_login_id("Jane", "Roe", joining)
        self.assertEqual(a[-4:], "0001")
        self.assertEqual(b[-4:], "0002")

        # And because it is COUNT()+1 with no uniqueness guard, two concurrent hires in
        # the same year compute the identical id.
        c1 = generate_login_id("Sam", "Poe", joining)
        c2 = generate_login_id("Sam", "Poe", joining)
        self.assertEqual(c1, c2, "expected the racy generator to repeat itself")
        print(f"\n[V-11] tenantA={a} tenantB={b} concurrent={c1}=={c2}")


class V12RefreshTokenAuthenticatesWebSocket(TestCase):
    """V-12: the WS middleware accepts a refresh token as if it were an access token."""

    def test_refresh_token_passes_the_ws_token_check(self):
        from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
        from rest_framework_simplejwt.settings import api_settings

        emp = mk_user("WSEMP", "Acme Corp")
        refresh = str(RefreshToken.for_user(emp))

        # realtime.auth validates with UntypedToken, which by design does not check the
        # "token_type" claim -- so a long-lived refresh token is accepted as WS credentials.
        validated = UntypedToken(refresh)
        self.assertEqual(validated["token_type"], "refresh")
        self.assertEqual(int(validated[api_settings.USER_ID_CLAIM]), emp.id)
        print("\n[V-12] UntypedToken accepted a", validated["token_type"], "token")


class V15MustChangePasswordBypass(TestCase):
    """V-15 FIXED: a pending password rotation blocks the whole API but the exits."""

    def setUp(self):
        self.emp = mk_user("TEMPPW", "Acme Corp", must_change_password=True)
        EmployeeSalary.objects.create(
            employee=self.emp, monthly_salary=Decimal("4000.00"), currency="INR"
        )
        resp = APIClient().post(
            "/api/auth/login/",
            {"login_id": "TEMPPW", "password": "Str0ngPassw0rd!42"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["must_change_password"])
        self.client_ = APIClient()
        self.client_.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_business_endpoints_are_blocked(self):
        for method, path in [
            ("get", "/api/dashboard/employee/"),
            ("get", "/api/payroll/salaries/"),
            ("get", "/api/accounts/employees/"),
            ("post", "/api/attendance/check-in/"),
            ("post", "/api/leave/apply/"),
        ]:
            with self.subTest(path=path):
                resp = getattr(self.client_, method)(path, {}, format="json")
                self.assertEqual(resp.status_code, 403, path)
                self.assertEqual(resp.data["detail"].code, "password_rotation_required")

    def test_change_password_remains_reachable(self):
        resp = self.client_.post(
            "/api/auth/change-password/",
            {"old_password": "Str0ngPassw0rd!42", "new_password": "An0therStr0ng!Pass"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(CustomUser.objects.get(pk=self.emp.pk).must_change_password)

        # Once rotated, the rest of the API opens up again.
        self.assertEqual(self.client_.get("/api/dashboard/employee/").status_code, 200)


class V16HardDeleteDestroysPayrollHistory(TestCase):
    """V-16: 'soft delete' is a hard delete that also wipes financial history."""

    def test_delete_employee_erases_paid_payroll(self):
        admin = mk_user("DELADMIN", "Acme Corp", role="ADMIN")
        emp = mk_user("DELEMP", "Acme Corp")
        sal = EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("6000.00"), currency="INR"
        )
        PayrollRecord.objects.create(
            employee=emp, salary=sal, month=date.today().replace(day=1),
            total_days_in_month=30, designated_salary=Decimal("6000.00"),
            net_salary=Decimal("6000.00"), status="PAID",
        )
        self.assertEqual(PayrollRecord.objects.count(), 1)

        resp = auth(admin).delete(f"/api/accounts/employees/{emp.id}/")
        self.assertEqual(resp.status_code, 204)

        # README promises is_active=False. Reality: the row and every paid payslip are gone.
        self.assertFalse(CustomUser.objects.filter(pk=emp.pk).exists())
        self.assertEqual(PayrollRecord.objects.count(), 0)
        self.assertEqual(EmployeeSalary.objects.count(), 0)


class V17HRPrivilegeCreep(TestCase):
    """V-17: HR inherits admin-grade powers, including deleting the company owner."""

    def test_hr_deletes_the_admin(self):
        admin = mk_user("OWNER", "Acme Corp", role="ADMIN")
        hr = mk_user("HRUSER", "Acme Corp", role="HR")

        # 'scope=non_admin' is gated to ADMIN, but the default queryset is not --
        # so HR simply omits the parameter and gets the owner row anyway.
        c = auth(hr)
        listing = c.get("/api/accounts/employees/")
        self.assertIn("OWNER", {e["login_id"] for e in listing.data["results"]})

        self.assertEqual(c.delete(f"/api/accounts/employees/{admin.id}/").status_code, 204)
        self.assertFalse(CustomUser.objects.filter(pk=admin.pk).exists())


class V18SalaryExposedInDirectory(TestCase):
    """V-18: the employee directory returns every colleague's salary field."""

    def test_salary_in_list_payload(self):
        hr = mk_user("SALHR", "Acme Corp", role="HR")
        mk_user("SALEMP", "Acme Corp", salary=Decimal("123456.00"))
        rows = auth(hr).get("/api/accounts/employees/").data["results"]
        target = next(r for r in rows if r["login_id"] == "SALEMP")
        self.assertEqual(str(target["salary"]), "123456.00")


class V19NoLoginRateLimit(TestCase):
    """V-19 FIXED: the login endpoint throttles repeated attempts."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    # SimpleRateThrottle.THROTTLE_RATES is bound as a class attribute when the module
    # is imported, so override_settings(REST_FRAMEWORK=...) cannot reach it. Patch the
    # class directly.
    @patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"login": "5/min"})
    def test_brute_force_is_throttled(self):
        mk_user("BRUTE", "Acme Corp")
        c = APIClient()
        codes = []
        for i in range(12):
            r = c.post(
                "/api/auth/login/",
                {"login_id": "BRUTE", "password": f"guess-{i}"},
                format="json",
            )
            codes.append(r.status_code)
        self.assertIn(429, codes, f"never throttled: {codes}")
        self.assertEqual(codes[-1], 429)
        print(f"\n[V-19] throttled after {codes.index(429)} failed attempts")

    def test_login_view_declares_a_throttle_scope(self):
        from auth_api.views import LoginAPIView

        self.assertEqual(LoginAPIView.throttle_scope, "login")
        self.assertTrue(
            any(isinstance(t, ScopedRateThrottle) for t in LoginAPIView().get_throttles())
        )


class V20PayrollRerunErasesPaymentAudit(TestCase):
    """V-20: re-running payroll silently flips PAID back to PENDING, losing the audit trail."""

    def test_rerun_resets_paid_record(self):
        admin = mk_user("RERUNADMIN", "Acme Corp", role="ADMIN")
        emp = mk_user("RERUNEMP", "Acme Corp")
        CompanyConfig.objects.create(company_name="Acme Corp", bypass_attendance=True)
        sal = EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("3000.00"), currency="INR"
        )
        month = date.today().replace(day=1)
        c = auth(admin)
        c.post("/api/payroll/run/", {"month": month.strftime("%Y-%m")}, format="json")
        rec = PayrollRecord.objects.get(employee=emp)
        c.post(f"/api/payroll/records/{rec.id}/credit/", {}, format="json")

        rec.refresh_from_db()
        self.assertEqual(rec.status, "PAID")
        self.assertIsNotNone(rec.credited_at)
        self.assertIsNotNone(rec.credited_by)

        # Same endpoint, no confirmation, no force flag needed.
        c.post("/api/payroll/run/", {"month": month.strftime("%Y-%m")}, format="json")
        rec.refresh_from_db()
        self.assertEqual(rec.status, "PENDING")
        self.assertIsNone(rec.credited_at)
        self.assertIsNone(rec.credited_by)
        print("\n[V-20] a credited payslip was silently reset to PENDING")


class V21ForceRecomputeIgnored(TestCase):
    """V-21: the documented force_recompute flag is parsed and then never used."""

    def test_flag_has_no_effect(self):
        import inspect
        from payroll import views as payroll_views
        src = inspect.getsource(payroll_views.PayrollRunAPIView)
        # It appears exactly twice, both on the assignment line -- the local is bound
        # and then never read, so passing the flag changes nothing.
        lines = [l for l in src.splitlines() if "force_recompute" in l]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("force_recompute = serializer.validated_data.get", lines[0])

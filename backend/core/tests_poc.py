"""Regression suite for every finding in docs/SECURITY_AUDIT.md.

Each class is named for its finding. A class docstring saying "FIXED" asserts the
secure behaviour and fails if the defect ever returns; one without it still
demonstrates a live defect and is expected to pass until its fix lands.

    python manage.py test core.tests_poc -v2
"""

from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from accounts.models import CustomUser
from attendance.models import Attendance
from leave.models import LeaveRequest
from organizations.models import Organization
from payroll.models import EmployeeSalary, PayrollRecord

PASSWORD = "Str0ngPassw0rd!42"


def mk_org(name="Acme Corp", **kw):
    from organizations.models import normalize_slug

    return Organization.objects.create(name=name, slug=normalize_slug(name), **kw)


def mk_user(login_id, organization, role="EMP", **kw):
    user = CustomUser.objects.create(
        login_id=login_id,
        email=f"{login_id.lower()}@{organization.slug}.test",
        organization=organization,
        role=role,
        **kw,
    )
    user.set_password(PASSWORD)
    user.save()
    return user


def auth(user):
    from rest_framework_simplejwt.tokens import RefreshToken

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def signup(company_name="New Co", email="founder@new.test", **extra):
    payload = {
        "first_name": "Fo",
        "last_name": "Under",
        "email": email,
        "password": PASSWORD,
        "company_name": company_name,
        **extra,
    }
    return APIClient().post("/api/accounts/register/", payload, format="json")


# ===========================================================================
# Critical
# ===========================================================================


class V01TenantTakeover(TestCase):
    """V-01 FIXED: signup creates a tenant and can never join an existing one."""

    def setUp(self):
        self.victim = mk_org("Acme Corp")
        self.victim_admin = mk_user("ACMEOWNER", self.victim, role="ADMIN")
        self.victim_emp = mk_user("ACMEEMP", self.victim)
        self.victim.owner = self.victim_admin
        self.victim.save()
        EmployeeSalary.objects.create(
            employee=self.victim_emp, monthly_salary=Decimal("9000.00"), currency="USD"
        )

    def test_signup_with_an_existing_company_name_is_rejected(self):
        resp = signup(company_name="Acme Corp", email="attacker@evil.test")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("already registered", str(resp.data).lower())
        self.assertFalse(CustomUser.objects.filter(email="attacker@evil.test").exists())

    def test_slug_equivalent_names_are_also_rejected(self):
        for variant in ["acme corp", "  Acme   Corp  ", "ACME-CORP", "Acme Corp"]:
            with self.subTest(variant=variant):
                resp = signup(company_name=variant, email=f"a{abs(hash(variant))}@evil.test")
                self.assertEqual(resp.status_code, 400, variant)

    def test_signup_creates_its_own_isolated_tenant(self):
        resp = signup(company_name="Evil Inc", email="attacker@evil.test")
        self.assertEqual(resp.status_code, 201, resp.data)
        attacker = CustomUser.objects.get(email="attacker@evil.test")
        self.assertEqual(attacker.role, "ADMIN")
        self.assertNotEqual(attacker.organization_id, self.victim.id)

        # The attacker is an admin -- of their own empty organization only.
        client = auth(attacker)
        listing = client.get("/api/accounts/employees/")
        self.assertEqual(listing.status_code, 200)
        logins = {row["login_id"] for row in listing.data["results"]}
        self.assertNotIn("ACMEEMP", logins)
        self.assertNotIn("ACMEOWNER", logins)

        salaries = client.get("/api/payroll/salaries/")
        self.assertEqual(salaries.status_code, 200)
        self.assertEqual(list(salaries.data), [])

    def test_cross_tenant_detail_lookup_is_404(self):
        outsider_org = mk_org("Evil Inc")
        outsider = mk_user("EVILADMIN", outsider_org, role="ADMIN")
        resp = auth(outsider).get(f"/api/accounts/employees/{self.victim_emp.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_signup_no_longer_grants_django_staff(self):
        signup(company_name="Staffless Co", email="nostaff@new.test")
        owner = CustomUser.objects.get(email="nostaff@new.test")
        self.assertFalse(owner.is_staff)
        self.assertFalse(owner.is_superuser)


class V02RegistrationLeaksTraceback(TestCase):
    """V-02 FIXED: internal errors return an opaque reference, never a traceback."""

    @patch(
        "accounts.serializers.Organization.objects.create",
        side_effect=RuntimeError("db exploded"),
    )
    def test_traceback_is_not_disclosed(self, _stub):
        with self.assertLogs("django.request", level="ERROR"):
            resp = signup(company_name="Trace Co", email="trace@evil.test")
        self.assertEqual(resp.status_code, 500)
        body = str(resp.data)
        self.assertNotIn("traceback", resp.data)
        self.assertNotIn('File "', body)
        self.assertNotIn("db exploded", body)
        self.assertNotIn("site-packages", body)
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
        self.assertFalse(CustomUser.objects.filter(email="admin1@gmail.com").exists())

    def test_no_backdoor_remains_in_source(self):
        import inspect

        from auth_api import serializers as auth_serializers

        src = inspect.getsource(auth_serializers)
        self.assertNotIn("adminisadmin", src)
        self.assertNotIn("admin1@gmail.com", src)
        self.assertNotIn("create_superuser", src)


class V10PaymentGrantsNothing(TestCase):
    """V-10: paying still grants no entitlement -- no Plan or Subscription exists."""

    def test_no_subscription_model_exists_yet(self):
        from django.apps import apps

        names = {m.__name__ for m in apps.get_models()}
        self.assertNotIn("Subscription", names)
        self.assertNotIn("Plan", names)


class V13PostgresOnlyRawSql(TestCase):
    """V-13 FIXED: the per-company raw-SQL shadow tables are gone."""

    def test_company_table_service_is_deleted(self):
        with self.assertRaises(ImportError):
            import accounts.company_table_service  # noqa: F401

    def test_signup_succeeds_without_postgres_specific_ddl(self):
        # This test runs on SQLite. Signup used to raise inside its atomic block
        # here, because the shadow table used BIGSERIAL/TIMESTAMPTZ/ON CONFLICT.
        resp = signup(company_name="Sqlite Works Co", email="sqlite@new.test")
        self.assertEqual(resp.status_code, 201, resp.data)


class V16HardDeleteDestroysPayrollHistory(TestCase):
    """V-16 FIXED: deletion deactivates and preserves every financial record."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.admin = mk_user("DELADMIN", self.org, role="ADMIN")
        self.org.owner = self.admin
        self.org.save()
        self.emp = mk_user("DELEMP", self.org)
        salary = EmployeeSalary.objects.create(
            employee=self.emp, monthly_salary=Decimal("6000.00"), currency="USD"
        )
        PayrollRecord.objects.create(
            employee=self.emp,
            salary=salary,
            month=date.today().replace(day=1),
            total_days_in_month=30,
            designated_salary=Decimal("6000.00"),
            net_salary=Decimal("6000.00"),
            status="PAID",
        )

    def test_delete_deactivates_and_keeps_history(self):
        resp = auth(self.admin).delete(f"/api/accounts/employees/{self.emp.id}/")
        self.assertEqual(resp.status_code, 204)

        self.emp.refresh_from_db()
        self.assertFalse(self.emp.is_active)
        self.assertEqual(PayrollRecord.objects.filter(employee=self.emp).count(), 1)
        self.assertEqual(EmployeeSalary.objects.filter(employee=self.emp).count(), 1)

    def test_deactivated_employee_leaves_the_directory_but_can_be_listed(self):
        auth(self.admin).delete(f"/api/accounts/employees/{self.emp.id}/")
        client = auth(self.admin)

        default = client.get("/api/accounts/employees/").data["results"]
        self.assertNotIn("DELEMP", {r["login_id"] for r in default})

        with_inactive = client.get("/api/accounts/employees/?include_inactive=true").data[
            "results"
        ]
        self.assertIn("DELEMP", {r["login_id"] for r in with_inactive})

    def test_owner_cannot_be_deactivated(self):
        other_admin = mk_user("SECONDADMIN", self.org, role="ADMIN")
        resp = auth(other_admin).delete(f"/api/accounts/employees/{self.admin.id}/")
        self.assertEqual(resp.status_code, 403)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_cannot_deactivate_yourself(self):
        resp = auth(self.admin).delete(f"/api/accounts/employees/{self.admin.id}/")
        self.assertEqual(resp.status_code, 403)


# ===========================================================================
# High
# ===========================================================================


class V06LeaveApprovalDestroysAttendance(TestCase):
    """V-06: approving leave still overwrites days the employee actually worked."""

    def test_approval_overwrites_present_day(self):
        org = mk_org("Acme Corp")
        admin = mk_user("OVERADMIN", org, role="ADMIN")
        emp = mk_user("OVEREMP", org)
        worked = date.today() - timedelta(days=1)
        Attendance.objects.create(user=emp, date=worked, status="PRESENT", total_hours=9.0)
        leave = LeaveRequest.objects.create(
            user=emp, leave_type="SICK", start_date=worked, end_date=worked, reason="x"
        )
        auth(admin).post(f"/api/leave/action/{leave.id}/", {"action": "APPROVE"}, format="json")

        attendance = Attendance.objects.get(user=emp, date=worked)
        self.assertEqual(attendance.status, "LEAVE")
        self.assertEqual(attendance.total_hours, 9.0)


class V07EmployeeSelfExpense(TestCase):
    """V-07: any employee can still post expenses against their own salary."""

    def test_employee_inflates_own_outstanding(self):
        org = mk_org("Acme Corp")
        emp = mk_user("SELFEXP", org)
        EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("5000.00"), currency="USD"
        )
        resp = auth(emp).post(
            "/api/payroll/salaries/add-expense/", {"amount": "999999.00"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(
            EmployeeSalary.objects.get(employee=emp).outstanding, Decimal("999999.00")
        )


class V09SlipXSS(TestCase):
    """V-09 FIXED: the salary slip escapes tenant-controlled data."""

    def setUp(self):
        self.payload = '"><script>alert(document.domain)</script>'
        self.org = mk_org(self.payload)
        # slugify() strips the payload, so give the org a deterministic slug.
        self.org.slug = "xss-test"
        self.org.name = self.payload
        self.org.save()
        self.admin = mk_user("XSSADMIN", self.org, role="ADMIN")
        emp = mk_user("XSSEMP", self.org)
        salary = EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("100.00"), currency="USD"
        )
        self.record = PayrollRecord.objects.create(
            employee=emp,
            salary=salary,
            month=date.today().replace(day=1),
            total_days_in_month=30,
            designated_salary=Decimal("100.00"),
            net_salary=Decimal("100.00"),
        )

    def test_company_name_is_escaped(self):
        resp = auth(self.admin).get(f"/api/payroll/slips/{self.record.id}/html/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"<script>alert(document.domain)</script>", resp.content)
        self.assertIn(b"&lt;script&gt;", resp.content)

    def test_slip_sets_a_restrictive_csp(self):
        resp = auth(self.admin).get(f"/api/payroll/slips/{self.record.id}/html/")
        self.assertIn("default-src 'none'", resp["Content-Security-Policy"])
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")

    def test_logo_url_must_be_https(self):
        resp = auth(self.admin).put(
            "/api/accounts/company-config/",
            {"logo_url": 'javascript:alert(1)//" onerror="alert(1)'},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("logo_url", resp.data)


class V15MustChangePasswordBypass(TestCase):
    """V-15 FIXED: a pending password rotation blocks the API but the exits."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.emp = mk_user("TEMPPW", self.org, must_change_password=True)
        EmployeeSalary.objects.create(
            employee=self.emp, monthly_salary=Decimal("4000.00"), currency="USD"
        )
        resp = APIClient().post(
            "/api/auth/login/", {"login_id": "TEMPPW", "password": PASSWORD}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["must_change_password"])
        self.client_ = APIClient()
        self.client_.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_business_endpoints_are_blocked(self):
        for method, path in [
            ("get", "/api/dashboard/employee/"),
            ("get", "/api/payroll/salaries/"),
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
            {"old_password": PASSWORD, "new_password": "An0therStr0ng!Pass"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(CustomUser.objects.get(pk=self.emp.pk).must_change_password)

        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.assertEqual(fresh.get("/api/dashboard/employee/").status_code, 200)

    def test_me_remains_reachable(self):
        self.assertEqual(self.client_.get("/api/auth/me/").status_code, 200)


class V17HRPrivilegeCreep(TestCase):
    """V-17 FIXED: HR cannot see, manage or deactivate an ADMIN."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.admin = mk_user("OWNER", self.org, role="ADMIN")
        self.org.owner = self.admin
        self.org.save()
        self.hr = mk_user("HRUSER", self.org, role="HR")

    def test_hr_directory_excludes_admins(self):
        rows = auth(self.hr).get("/api/accounts/employees/").data["results"]
        self.assertNotIn("OWNER", {r["login_id"] for r in rows})

    def test_hr_cannot_read_the_admin_record(self):
        self.assertEqual(
            auth(self.hr).get(f"/api/accounts/employees/{self.admin.id}/").status_code, 403
        )

    def test_hr_cannot_deactivate_the_admin(self):
        self.assertEqual(
            auth(self.hr).delete(f"/api/accounts/employees/{self.admin.id}/").status_code, 403
        )
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_hr_cannot_change_company_settings(self):
        resp = auth(self.hr).put(
            "/api/accounts/company-config/", {"bypass_attendance": True}, format="json"
        )
        self.assertEqual(resp.status_code, 403)

    def test_hr_cannot_create_another_hr(self):
        resp = auth(self.hr).post(
            "/api/auth/create-employee/",
            {
                "first_name": "New",
                "last_name": "Hr",
                "email": "newhr@acme.test",
                "role": "HR",
                "date_of_joining": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_can_still_manage_everything(self):
        client = auth(self.admin)
        rows = client.get("/api/accounts/employees/").data["results"]
        self.assertIn("HRUSER", {r["login_id"] for r in rows})
        self.assertEqual(
            client.put(
                "/api/accounts/company-config/", {"bypass_attendance": True}, format="json"
            ).status_code,
            200,
        )


class V19NoLoginRateLimit(TestCase):
    """V-19 FIXED: the login endpoint throttles repeated attempts."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"login": "5/min"})
    def test_brute_force_is_throttled(self):
        mk_user("BRUTE", mk_org("Acme Corp"))
        client = APIClient()
        codes = [
            client.post(
                "/api/auth/login/", {"login_id": "BRUTE", "password": f"g{i}"}, format="json"
            ).status_code
            for i in range(12)
        ]
        self.assertIn(429, codes, f"never throttled: {codes}")
        self.assertEqual(codes[-1], 429)


class V20PayrollRerunErasesPaymentAudit(TestCase):
    """V-20: re-running payroll still flips PAID back to PENDING."""

    def test_rerun_resets_paid_record(self):
        org = mk_org("Acme Corp", bypass_attendance=True)
        admin = mk_user("RERUNADMIN", org, role="ADMIN")
        emp = mk_user("RERUNEMP", org)
        EmployeeSalary.objects.create(
            employee=emp, monthly_salary=Decimal("3000.00"), currency="USD"
        )
        month = date.today().replace(day=1).strftime("%Y-%m")
        client = auth(admin)
        client.post("/api/payroll/run/", {"month": month}, format="json")
        record = PayrollRecord.objects.get(employee=emp)
        client.post(f"/api/payroll/records/{record.id}/credit/", {}, format="json")

        record.refresh_from_db()
        self.assertEqual(record.status, "PAID")

        client.post("/api/payroll/run/", {"month": month}, format="json")
        record.refresh_from_db()
        self.assertEqual(record.status, "PENDING")
        self.assertIsNone(record.credited_at)


class V27NoPasswordReset(TestCase):
    """V-27 FIXED: self-service password reset exists and does not enumerate users."""

    def setUp(self):
        cache.clear()
        self.org = mk_org("Acme Corp")
        self.emp = mk_user("RESETME", self.org)

    def tearDown(self):
        cache.clear()

    def test_reset_email_is_sent(self):
        resp = APIClient().post(
            "/api/auth/password-reset/", {"email": self.emp.email}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset-password?uid=", mail.outbox[0].body)

    def test_unknown_email_gets_an_identical_response(self):
        known = APIClient().post(
            "/api/auth/password-reset/", {"email": self.emp.email}, format="json"
        )
        unknown = APIClient().post(
            "/api/auth/password-reset/", {"email": "nobody@nowhere.test"}, format="json"
        )
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_link_sets_a_new_password(self):
        APIClient().post("/api/auth/password-reset/", {"email": self.emp.email}, format="json")
        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].split()[0]

        resp = APIClient().post(
            "/api/auth/password-reset/confirm/",
            {"uid": uid, "token": token, "new_password": "Br@ndNewP4ssword"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)

        login = APIClient().post(
            "/api/auth/login/",
            {"login_id": "RESETME", "password": "Br@ndNewP4ssword"},
            format="json",
        )
        self.assertEqual(login.status_code, 200)

    def test_a_used_token_cannot_be_replayed(self):
        APIClient().post("/api/auth/password-reset/", {"email": self.emp.email}, format="json")
        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].split()[0]
        payload = {"uid": uid, "token": token, "new_password": "Br@ndNewP4ssword"}

        self.assertEqual(
            APIClient().post("/api/auth/password-reset/confirm/", payload, format="json").status_code,
            200,
        )
        self.assertEqual(
            APIClient().post("/api/auth/password-reset/confirm/", payload, format="json").status_code,
            400,
        )


# ===========================================================================
# Medium
# ===========================================================================


class V04CheckoutCrash(TestCase):
    """V-04 FIXED: check-out with no check-in is a clean 400, not a 500."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.emp = mk_user("CRASHEMP", self.org)

    def test_checkout_on_a_leave_row_is_rejected_cleanly(self):
        # Approving leave creates a row with check_in=None; this used to crash.
        Attendance.objects.create(user=self.emp, date=self.org.today(), status="LEAVE")
        resp = auth(self.emp).post("/api/attendance/check-out/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not checked in", resp.data["detail"])

    def test_checkout_with_no_row_at_all_is_rejected_cleanly(self):
        resp = auth(self.emp).post("/api/attendance/check-out/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No check-in found", resp.data["detail"])

    def test_the_happy_path_still_works(self):
        client = auth(self.emp)
        self.assertEqual(client.post("/api/attendance/check-in/", {}, format="json").status_code, 200)
        resp = client.post("/api/attendance/check-out/", {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIsNotNone(resp.data["total_hours"])

    def test_double_checkout_is_rejected(self):
        client = auth(self.emp)
        client.post("/api/attendance/check-in/", {}, format="json")
        client.post("/api/attendance/check-out/", {}, format="json")
        resp = client.post("/api/attendance/check-out/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Already checked out", resp.data["detail"])


class V05LeaveDateValidation(TestCase):
    """V-05 FIXED: leave ranges are ordered, bounded, and cannot be open-ended."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.emp = mk_user("LEAVEVAL", self.org)
        self.client_ = auth(self.emp)

    def _apply(self, start, end, leave_type="CASUAL"):
        return self.client_.post(
            "/api/leave/apply/",
            {
                "leave_type": leave_type,
                "start_date": str(start),
                "end_date": str(end),
                "reason": "a valid reason",
            },
            format="json",
        )

    def test_reversed_range_is_rejected(self):
        today = self.org.today()
        resp = self._apply(today + timedelta(days=30), today + timedelta(days=1))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("end_date", resp.data)

    def test_decade_long_leave_is_rejected(self):
        today = self.org.today()
        resp = self._apply(today + timedelta(days=1), today + timedelta(days=3650))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("end_date", resp.data)

    def test_ancient_backdating_is_rejected(self):
        today = self.org.today()
        resp = self._apply(today - timedelta(days=400), today - timedelta(days=398))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("start_date", resp.data)

    def test_far_future_leave_is_rejected(self):
        today = self.org.today()
        resp = self._apply(today + timedelta(days=800), today + timedelta(days=802))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("start_date", resp.data)

    def test_an_empty_reason_is_rejected(self):
        today = self.org.today()
        resp = self.client_.post(
            "/api/leave/apply/",
            {
                "leave_type": "CASUAL",
                "start_date": str(today + timedelta(days=1)),
                "end_date": str(today + timedelta(days=2)),
                "reason": "  ",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("reason", resp.data)

    def test_a_reasonable_request_is_accepted(self):
        today = self.org.today()
        resp = self._apply(today + timedelta(days=1), today + timedelta(days=3))
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["leave"]["total_days"], 3)


class V06LeaveApprovalDestroysAttendance(TestCase):
    """V-06 FIXED: approval can never overwrite a day the employee worked."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.admin = mk_user("OVERADMIN", self.org, role="ADMIN")
        self.org.owner = self.admin
        self.org.save()
        self.emp = mk_user("OVEREMP", self.org)

    def test_approval_is_refused_when_the_range_contains_a_worked_day(self):
        worked = self.org.today() - timedelta(days=1)
        Attendance.objects.create(
            user=self.emp, date=worked, status="PRESENT", total_hours=9.0,
            check_in=timezone.now() - timedelta(days=1),
        )
        leave = LeaveRequest.objects.create(
            user=self.emp, leave_type="SICK", start_date=worked, end_date=worked, reason="x"
        )
        resp = auth(self.admin).post(
            f"/api/leave/action/{leave.id}/", {"action": "APPROVE"}, format="json"
        )
        self.assertEqual(resp.status_code, 409)

        attendance = Attendance.objects.get(user=self.emp, date=worked)
        self.assertEqual(attendance.status, "PRESENT")
        self.assertEqual(attendance.total_hours, 9.0)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "PENDING")

    def test_applying_over_a_worked_day_is_refused_up_front(self):
        worked = self.org.today() - timedelta(days=1)
        Attendance.objects.create(
            user=self.emp, date=worked, status="PRESENT", total_hours=9.0,
            check_in=timezone.now() - timedelta(days=1),
        )
        resp = auth(self.emp).post(
            "/api/leave/apply/",
            {
                "leave_type": "SICK",
                "start_date": str(worked),
                "end_date": str(worked),
                "reason": "felt unwell",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("recorded attendance", resp.data["detail"])

    def test_a_clean_approval_marks_leave_and_clears_stale_times(self):
        start = self.org.today() + timedelta(days=1)
        end = start + timedelta(days=2)
        # A row exists for one of the days, but with no check-in.
        Attendance.objects.create(user=self.emp, date=start, status="ABSENT", total_hours=3.0)
        leave = LeaveRequest.objects.create(
            user=self.emp, leave_type="PAID", start_date=start, end_date=end, reason="x"
        )
        resp = auth(self.admin).post(
            f"/api/leave/action/{leave.id}/", {"action": "APPROVE"}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["days_marked"], 3)

        for row in Attendance.objects.filter(user=self.emp, date__gte=start, date__lte=end):
            self.assertEqual(row.status, "LEAVE")
            self.assertIsNone(row.check_in)
            self.assertEqual(row.total_hours, 0.0)

    def test_nobody_approves_their_own_leave(self):
        hr = mk_user("SELFHR", self.org, role="HR")
        start = self.org.today() + timedelta(days=1)
        leave = LeaveRequest.objects.create(
            user=hr, leave_type="CASUAL", start_date=start, end_date=start, reason="x"
        )
        resp = auth(hr).post(f"/api/leave/action/{leave.id}/", {"action": "APPROVE"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_a_decided_request_cannot_be_decided_again(self):
        start = self.org.today() + timedelta(days=1)
        leave = LeaveRequest.objects.create(
            user=self.emp, leave_type="CASUAL", start_date=start, end_date=start, reason="x"
        )
        client = auth(self.admin)
        self.assertEqual(
            client.post(f"/api/leave/action/{leave.id}/", {"action": "REJECT"}, format="json").status_code,
            200,
        )
        resp = client.post(f"/api/leave/action/{leave.id}/", {"action": "APPROVE"}, format="json")
        self.assertEqual(resp.status_code, 400)


class V26TimezoneHandling(TestCase):
    """V-26 FIXED: the working day is resolved in the organization's timezone."""

    def test_organization_today_uses_its_own_zone(self):
        from unittest.mock import patch as _patch

        kolkata = mk_org("Kolkata Co", timezone="Asia/Kolkata")
        honolulu = mk_org("Honolulu Co", timezone="Pacific/Honolulu")

        # 2026-06-15 20:00 UTC: already the 16th in Kolkata, still the 15th in Honolulu.
        moment = datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
        with _patch("django.utils.timezone.now", return_value=moment):
            self.assertEqual(kolkata.today(), date(2026, 6, 16))
            self.assertEqual(honolulu.today(), date(2026, 6, 15))

    def test_checkin_is_recorded_against_the_org_day(self):
        from unittest.mock import patch as _patch

        org = mk_org("Kolkata Co", timezone="Asia/Kolkata")
        emp = mk_user("TZEMP", org)
        moment = datetime(2026, 6, 15, 20, 0, tzinfo=dt_timezone.utc)
        with _patch("django.utils.timezone.now", return_value=moment):
            resp = auth(emp).post("/api/attendance/check-in/", {}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(Attendance.objects.get(user=emp).date, date(2026, 6, 16))

    def test_an_invalid_org_timezone_falls_back_to_utc(self):
        org = mk_org("Broken Co")
        Organization.objects.filter(pk=org.pk).update(timezone="Not/AZone")
        org.refresh_from_db()
        self.assertEqual(org.today(), timezone.now().date())


class V28UnboundedHistoryQueries(TestCase):
    """V-28 FIXED: history endpoints are bounded, filterable and paginated."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.admin = mk_user("HISTADMIN", self.org, role="ADMIN")
        self.emp = mk_user("HISTEMP", self.org)
        today = self.org.today()
        Attendance.objects.bulk_create(
            [
                Attendance(user=self.emp, date=today - timedelta(days=i), status="PRESENT")
                for i in range(200)
            ]
        )

    def test_default_window_does_not_return_everything(self):
        rows = auth(self.emp).get("/api/attendance/my/").data
        self.assertIn("count", rows)
        self.assertLess(rows["count"], 200)

    def test_an_explicit_range_is_honoured(self):
        today = self.org.today()
        resp = auth(self.emp).get(
            f"/api/attendance/my/?start_date={today - timedelta(days=6)}&end_date={today}"
        )
        self.assertEqual(resp.data["count"], 7)

    def test_an_oversized_range_is_rejected(self):
        today = self.org.today()
        resp = auth(self.emp).get(
            f"/api/attendance/my/?start_date={today - timedelta(days=800)}&end_date={today}"
        )
        self.assertEqual(resp.status_code, 400)

    def test_a_reversed_range_is_rejected(self):
        today = self.org.today()
        resp = auth(self.emp).get(
            f"/api/attendance/my/?start_date={today}&end_date={today - timedelta(days=7)}"
        )
        self.assertEqual(resp.status_code, 400)

    def test_admins_are_no_longer_excluded_from_oversight(self):
        Attendance.objects.create(user=self.admin, date=self.org.today(), status="PRESENT")
        rows = auth(self.admin).get("/api/attendance/all/").data["results"]
        self.assertIn("HISTADMIN", {r["user_login_id"] for r in rows})

    def test_results_can_be_filtered_to_one_employee(self):
        resp = auth(self.admin).get(f"/api/attendance/all/?employee_id={self.emp.id}")
        self.assertTrue(all(r["user"] == self.emp.id for r in resp.data["results"]))


class V08NegativeNetSalary(TestCase):
    """V-08: payroll can still compute a negative net salary."""

    def test_payroll_goes_negative(self):
        org = mk_org("Acme Corp", bypass_attendance=True)
        admin = mk_user("NEGADMIN", org, role="ADMIN")
        emp = mk_user("NEGEMP", org)
        EmployeeSalary.objects.create(
            employee=emp,
            monthly_salary=Decimal("1000.00"),
            currency="USD",
            outstanding=Decimal("50000.00"),
        )
        month = date.today().replace(day=1).strftime("%Y-%m")
        resp = auth(admin).post("/api/payroll/run/", {"month": month}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertLess(PayrollRecord.objects.get(employee=emp).net_salary, Decimal("0.00"))


class V11LoginIdCollision(TestCase):
    """V-11 FIXED: login ids are per-organization, sequential only within a tenant."""

    def test_counter_is_per_organization(self):
        from accounts.utils import generate_login_id

        org_a = mk_org("Alpha Co")
        org_b = mk_org("Beta Co")

        a1 = generate_login_id(org_a, "John", "Doe")
        b1 = generate_login_id(org_b, "Jane", "Roe")
        a2 = generate_login_id(org_a, "Sam", "Poe")

        # Each organization counts from one: no cross-tenant information leak.
        self.assertTrue(a1.endswith("00001"), a1)
        self.assertTrue(b1.endswith("00001"), b1)
        self.assertTrue(a2.endswith("00002"), a2)
        self.assertTrue(a1.startswith("ALP"))
        self.assertTrue(b1.startswith("BET"))

    def test_repeated_generation_never_repeats_an_id(self):
        from accounts.utils import generate_login_id

        org = mk_org("Alpha Co")
        ids = [generate_login_id(org, "Sam", "Poe") for _ in range(25)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_temp_passwords_use_a_csprng(self):
        import inspect

        from accounts import utils

        # Inspect the function body, not the module docstring (which names the old call).
        src = inspect.getsource(utils.generate_temp_password)
        self.assertIn("secrets.choice", src)
        self.assertNotIn("random.", src)
        self.assertGreaterEqual(len(utils.generate_temp_password()), 16)


class V12RefreshTokenAuthenticatesWebSocket(TestCase):
    """V-12: the WS middleware still accepts a refresh token as credentials."""

    def test_refresh_token_passes_the_ws_token_check(self):
        from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken

        emp = mk_user("WSEMP", mk_org("Acme Corp"))
        validated = UntypedToken(str(RefreshToken.for_user(emp)))
        self.assertEqual(validated["token_type"], "refresh")


class V18SalaryExposedInDirectory(TestCase):
    """V-18 FIXED: the directory and its export carry no compensation data."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.hr = mk_user("SALHR", self.org, role="HR")
        self.emp = mk_user("SALEMP", self.org)
        EmployeeSalary.objects.create(
            employee=self.emp, monthly_salary=Decimal("123456.00"), currency="USD"
        )

    def test_salary_absent_from_the_directory(self):
        rows = auth(self.hr).get("/api/accounts/employees/").data["results"]
        target = next(r for r in rows if r["login_id"] == "SALEMP")
        self.assertNotIn("salary", target)

    def test_salary_absent_from_the_export(self):
        resp = auth(self.hr).get("/api/accounts/employees/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(b"123456", resp.content)

    def test_user_model_no_longer_carries_a_salary_column(self):
        self.assertFalse(hasattr(CustomUser(), "salary"))


class V25CompanyConfigOrphansRoles(TestCase):
    """V-25 FIXED: settings cannot drop a role or department still in use."""

    def setUp(self):
        self.org = mk_org("Acme Corp")
        self.org.roles = ["EMP", "HR"]
        self.org.departments = ["Engineering", "Sales"]
        self.org.save()
        self.admin = mk_user("CFGADMIN", self.org, role="ADMIN")
        mk_user("CFGEMP", self.org, role="EMP", department="Engineering")

    def test_cannot_remove_a_role_in_use(self):
        resp = auth(self.admin).put(
            "/api/accounts/company-config/", {"roles": ["HR"]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("roles", resp.data)

    def test_cannot_remove_a_department_in_use(self):
        resp = auth(self.admin).put(
            "/api/accounts/company-config/", {"departments": ["Sales"]}, format="json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("departments", resp.data)

    def test_can_remove_an_unused_department(self):
        resp = auth(self.admin).put(
            "/api/accounts/company-config/",
            {"departments": ["Engineering"]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)


# ===========================================================================
# Low
# ===========================================================================


class V21ForceRecomputeIgnored(TestCase):
    """V-21: the documented force_recompute flag is still parsed and ignored."""

    def test_flag_has_no_effect(self):
        import inspect

        from payroll import views as payroll_views

        src = inspect.getsource(payroll_views.PayrollRunAPIView)
        lines = [line for line in src.splitlines() if "force_recompute" in line]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("force_recompute = serializer.validated_data.get", lines[0])


# ===========================================================================
# Cross-cutting tenancy checks
# ===========================================================================


class TenantIsolation(TestCase):
    """Every list endpoint must be scoped to the caller's organization."""

    def setUp(self):
        self.org_a = mk_org("Alpha Co")
        self.admin_a = mk_user("ALPHAADMIN", self.org_a, role="ADMIN")
        self.emp_a = mk_user("ALPHAEMP", self.org_a)

        self.org_b = mk_org("Beta Co")
        self.admin_b = mk_user("BETAADMIN", self.org_b, role="ADMIN")
        self.emp_b = mk_user("BETAEMP", self.org_b)

        for emp in (self.emp_a, self.emp_b):
            Attendance.objects.create(user=emp, date=date.today(), status="PRESENT")
            LeaveRequest.objects.create(
                user=emp,
                leave_type="CASUAL",
                start_date=date.today(),
                end_date=date.today(),
                reason="r",
            )
            salary = EmployeeSalary.objects.create(
                employee=emp, monthly_salary=Decimal("1000.00"), currency="USD"
            )
            PayrollRecord.objects.create(
                employee=emp,
                salary=salary,
                month=date.today().replace(day=1),
                total_days_in_month=30,
                designated_salary=Decimal("1000.00"),
                net_salary=Decimal("1000.00"),
            )

    def _ids(self, payload):
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return rows

    def test_admin_a_sees_only_alpha_records(self):
        client = auth(self.admin_a)

        employees = self._ids(client.get("/api/accounts/employees/").data)
        # An owner sees the full roster of their own organization, and nobody else's.
        self.assertEqual({r["login_id"] for r in employees}, {"ALPHAEMP", "ALPHAADMIN"})

        attendance = self._ids(client.get("/api/attendance/all/").data)
        self.assertTrue(all(r["user_login_id"].startswith("ALPHA") for r in attendance))

        leaves = self._ids(client.get("/api/leave/all/").data)
        self.assertTrue(all(r["user"] in (self.emp_a.id, self.admin_a.id) for r in leaves))

        payroll = self._ids(client.get("/api/payroll/records/").data)
        self.assertTrue(all(r["employee_id"] == self.emp_a.id for r in payroll))

        salaries = self._ids(client.get("/api/payroll/salaries/").data)
        self.assertTrue(all(r["employee_id"] == self.emp_a.id for r in salaries))

    def test_admin_cannot_approve_another_tenants_leave(self):
        other_leave = LeaveRequest.objects.filter(user=self.emp_b).first()
        resp = auth(self.admin_a).post(
            f"/api/leave/action/{other_leave.id}/", {"action": "APPROVE"}, format="json"
        )
        self.assertEqual(resp.status_code, 404)
        other_leave.refresh_from_db()
        self.assertEqual(other_leave.status, "PENDING")

    def test_admin_cannot_credit_another_tenants_payroll(self):
        other = PayrollRecord.objects.get(employee=self.emp_b)
        resp = auth(self.admin_a).post(
            f"/api/payroll/records/{other.id}/credit/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 404)

    def test_admin_cannot_read_another_tenants_payslip(self):
        other = PayrollRecord.objects.get(employee=self.emp_b)
        self.assertEqual(auth(self.admin_a).get(f"/api/payroll/slips/{other.id}/").status_code, 404)

    def test_admin_cannot_set_salary_for_another_tenants_employee(self):
        resp = auth(self.admin_a).post(
            "/api/payroll/salaries/",
            {"employee_id": self.emp_b.id, "monthly_salary": "1.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_user_without_an_organization_is_refused(self):
        orphan = CustomUser.objects.create(login_id="ORPHAN", email="o@o.test", role="ADMIN")
        orphan.set_password(PASSWORD)
        orphan.save()
        resp = auth(orphan).get("/api/accounts/employees/")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("not linked to an organization", str(resp.data))

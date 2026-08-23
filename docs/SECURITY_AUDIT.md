# DayFlow — Security & Correctness Audit

**Audit date:** 2026-08-23
**Scope:** `backend/` (Django 4.2 + DRF + Channels), `frontend/` (React 18 + Vite + Electron)
**Baseline commit:** `436babf1` on branch `prod`
**Method:** full source review of every backend app and every frontend API/auth path, plus an
executable proof-of-vulnerability suite.

---

## How to reproduce

Every finding marked **PoC** has an executable test that **passes while the defect is present**.

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements.txt
DATABASE_URL= DB_NAME= .venv/bin/python manage.py test core.tests_poc -v2
```

Baseline result (pre-fix):

```
Ran 20 tests in 5.540s
OK
```

All 20 passing means all 20 defects are live. As each fix lands, its test is inverted into a
regression test that fails if the defect ever returns.

> The suite runs against SQLite with `DATABASE_URL=` blanked so it never touches the production
> Postgres instance configured in `backend/.env`.

---

## Summary

| Severity | Count | Findings |
|---|---|---|
| **Critical** | 5 | V-01, V-03, V-10, V-13, V-16 |
| **High** | 9 | V-02, V-06, V-07, V-09, V-15, V-17, V-19, V-20, V-27 |
| **Medium** | 12 | V-04, V-05, V-08, V-11, V-12, V-14, V-18, V-22, V-23, V-24, V-26, V-30 |
| **Low** | 8 | V-21, V-25, V-28, V-29, V-31, V-32, V-33, V-34 |
| **Total** | **34** | |

**The single most serious issue is V-01.** Any person on the internet can take over any
existing customer's tenant — reading every employee record, salary, and payslip — with one
unauthenticated HTTP request and no credentials.

---

## Critical

### V-01 — Unauthenticated tenant takeover via public registration
**PoC:** `V01TenantTakeover` · **Location:** `backend/accounts/views.py:51-90`, `backend/accounts/serializers.py:5-49`

`POST /api/accounts/register/` is `AllowAny`. It accepts an arbitrary `company_name` string and
then unconditionally promotes the new account:

```python
user.role = "ADMIN"
user.is_staff = True
user.is_approved = True
```

Tenancy is nothing more than a `company_name` **string comparison** (`CustomUser.company_name`,
a plain `CharField`). Every authorization check in the codebase is
`filter(company_name=request.user.company_name)`. So supplying an existing customer's company
name during signup grants full administrative control of that customer's tenant.

**Exploit — no authentication required:**

```bash
curl -X POST https://dayfllow.onrender.com/api/accounts/register/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"attacker@evil.test","password":"Str0ngPassw0rd!42",
       "first_name":"Mal","last_name":"Lory","company_name":"Acme Corp"}'
# -> 201, attacker is now ADMIN of "Acme Corp"
```

The attacker can then read the full employee directory, every salary, every payslip, approve or
reject leave, run payroll, and delete the real owner's account (see V-17).

**Impact:** Complete cross-tenant compromise of confidentiality, integrity and availability.
Company names are public information, so target selection is trivial.

**Fix:** Replace the string tenant key with a real `Organization` model and FK; make the first
signup *create* an organization and fail if the slug is taken; make all subsequent joins
invitation-only. Never derive tenancy from user-supplied text.

---

### V-03 — Hardcoded credential backdoor mints a superuser
**PoC:** `V03LoginBackdoor` · **Location:** `backend/auth_api/serializers.py:23-37`

```python
# Development-only backdoor: accept specific credentials as admin
if (settings.DEBUG
        and data.get("login_id") == "admin1@gmail.com"
        and data.get("password") == "adminisadmin"):
    user = CustomUser.objects.filter(email=data.get("login_id")).first()
    if not user:
        user = CustomUser.objects.create_superuser(...)
```

The credentials bypass `authenticate()` entirely and **create a Django superuser on demand** if
one does not already exist. `DEBUG` defaults to `True` (`settings.py:36`,
`os.getenv("DJANGO_DEBUG", "True")`), so any deployment that forgets to set the variable ships
this backdoor live. The credentials are in a public Git repository.

**Impact:** Full platform compromise — superuser access to `/admin/` and every tenant's data.

**Fix:** Delete the branch outright. Seed development data with `manage.py createsuperuser` or a
fixture, never with a login-path special case.

---

### V-10 — Payment verification grants no entitlement and is unauthenticated
**PoC:** `V10PaymentGrantsNothing` · **Location:** `backend/accounts/views.py:263-347`

`RazorpayCreateOrderAPIView` and `RazorpayVerifyPaymentAPIView` are both `AllowAny`, and the
verify endpoint's entire success path is:

```python
return Response({"message": "Payment verified successfully."}, status=200)
```

No `Subscription` model exists. No `Plan` model exists. Nothing is written to the database.
Consequences:

* **Paying customers get nothing.** A successful payment is not recorded anywhere; the account
  is provisioned by signup alone.
* **Non-paying users get everything.** Signup never checks payment status, so the entire
  checkout flow is decorative — skipping it grants identical access.
* Verification is client-driven with no webhook, so a dropped browser connection loses the
  payment silently even if it had been recorded.
* The endpoint is unauthenticated, so it cannot associate a payment with an account even in
  principle.

**Impact:** 100% revenue loss; the product is not actually a paid service.

**Fix:** Real `Plan`/`Subscription`/`Invoice` models, Stripe Checkout, server-side webhook as
the *only* source of subscription truth, and entitlement enforcement on protected endpoints.

---

### V-13 — Application is Postgres-only but silently defaults to SQLite
**Location:** `backend/accounts/company_table_service.py:18-107`, `backend/core/settings.py:120-155`

`ensure_company_table()` executes raw DDL using Postgres-only syntax (`BIGSERIAL`,
`TIMESTAMPTZ`, `ADD COLUMN IF NOT EXISTS`, `ON CONFLICT`). Meanwhile `settings.py` falls back to
SQLite whenever `DATABASE_URL` and the `DB_*` variables are unset — which is the documented
local-setup path in the README.

On SQLite, `POST /api/accounts/register/` raises inside `transaction.atomic()`, the transaction
rolls back, and **signup is completely broken**. Confirmed during this audit: registration only
succeeds once the raw-SQL calls are stubbed out.

Separately, this "table per company" design is an anti-pattern — it creates unbounded DDL from
user input, cannot be migrated, is invisible to the ORM, has no foreign keys, and duplicates data
that already lives in `accounts_customuser`. It is written on signup and on employee creation but
**never read by any query in the codebase**. It is pure liability.

**Impact:** Onboarding fails outright on the documented local setup; unbounded schema growth and
an unmigratable, unqueryable shadow copy of user PII in production.

**Fix:** Delete `company_table_service.py` entirely and make Postgres a hard requirement.

---

### V-16 — "Soft delete" is a hard delete that destroys financial records
**PoC:** `V16HardDeleteDestroysPayrollHistory` · **Location:** `backend/accounts/views.py:101-118`

The README states: *"Soft-delete approach using `is_active` flag — Employee records are never
destroyed, preserving historical integrity."* The implementation does the opposite:

```python
def perform_destroy(self, instance):
    PayrollRecord.objects.filter(employee=instance).delete()
    EmployeeSalary.objects.filter(employee=instance).delete()
    delete_company_user_row(instance.company_name, instance.id)
    instance.delete()
```

`DELETE /api/accounts/employees/<id>/` permanently removes the user **and every payroll record,
including those already marked `PAID`**. `PayrollRecord.salary` is declared `on_delete=PROTECT`
specifically to prevent this, and the view defeats the protection by deleting children first.
`Attendance` and `LeaveRequest` then cascade away too.

**Impact:** Irreversible destruction of payroll and tax records. In most jurisdictions payroll
data carries a multi-year statutory retention requirement, so this is a compliance breach as
well as a data-loss bug. Any HR user can trigger it (V-17).

**Fix:** Set `is_active = False`, keep every row, exclude inactive users from directory queries,
and reserve real deletion for a separate audited retention job.

---

## High

### V-02 — Registration returns a full Python traceback to unauthenticated callers
**PoC:** `V02RegistrationLeaksTraceback` · **Location:** `backend/accounts/views.py:74-80`

```python
except Exception as e:
    tb = traceback.format_exc()
    return Response({"detail": str(e), "traceback": tb}, status=500)
```

This runs regardless of `DEBUG`. Combined with V-13 the error path is easy to trigger, and the
response discloses absolute filesystem paths, the dependency tree with versions, internal module
layout, and SQL fragments — a ready-made map for further attacks.

**Fix:** Log server-side with a correlation id; return an opaque error to the client.

---

### V-06 — Leave approval destroys attendance history
**PoC:** `V06LeaveApprovalDestroysAttendance` · **Location:** `backend/leave/views.py:102-111`

```python
Attendance.objects.update_or_create(
    user=leave.user, date=current, defaults={"status": "LEAVE"}
)
```

`update_or_create` overwrites **existing** attendance rows. Approving a backdated leave request
that overlaps days the employee actually worked rewrites those days to `LEAVE` while leaving the
stale `check_in`, `check_out` and `total_hours` values in place — the record becomes internally
contradictory (status `LEAVE`, 9 hours worked).

Because payroll counts `status="PRESENT"` days (`payroll/views.py:44-50`), those worked days
stop being payable. **An approved leave request silently reduces an employee's pay for days they
were physically at work.**

**Fix:** Refuse to overwrite days with a recorded check-in; validate at application time that the
range contains no worked days; clear the time fields when a day legitimately becomes `LEAVE`.

---

### V-07 — Employees can post unlimited expenses against their own salary
**PoC:** `V07EmployeeSelfExpense` · **Location:** `backend/payroll/views.py:401-448`

`POST /api/payroll/salaries/add-expense/` only checks `_is_payroll_manager` when an
`employee_id` is supplied. Omitting it defaults to `employee = request.user`, so **any employee
can write directly to their own `EmployeeSalary.outstanding`** with no approval, no cap, no
audit record, and no receipt.

Combined with V-08 this is a direct financial-integrity failure in both directions: an employee
can zero out their own net pay, or a malicious insider can inflate a colleague's outstanding
balance. There is no way to reverse an entry.

**Fix:** Expense submission must be a separate reviewable model with `PENDING/APPROVED/REJECTED`
states; only an approver may move an amount into `outstanding`.

---

### V-09 — Stored XSS in the HTML salary slip
**PoC:** `V09SlipXSS` · **Location:** `backend/payroll/views.py:332-398`

The slip is built with an f-string and **no escaping**:

```python
f'<img src="{logo.logo_url}" ...'
...
<div><strong>Company:</strong> {payroll.employee.company_name}</div>
```

Both `company_name` (set by the tenant at signup, V-01) and `logo_url` (set via
`PUT /api/accounts/company-config/`) are attacker-controlled and land unescaped in an
`HttpResponse` served as `text/html` from the API origin. Confirmed: a `company_name` of
`"><script>alert(document.domain)</script>` executes.

`logo_url` is worse — it is injected into an attribute, so `" onerror="fetch(...)` escapes the
attribute without needing `<script>`.

**Impact:** Script execution on the API origin against any admin or employee who views a payslip.
Since JWTs are kept in `localStorage` (V-23), a single payload exfiltrates a session token.

**Fix:** Render via a Django template with autoescaping on; validate `logo_url` scheme against an
`https://` allowlist.

---

### V-15 — `must_change_password` is never enforced
**PoC:** `V15MustChangePasswordBypass` · **Location:** `backend/auth_api/views.py:12-34`, all views

Login returns `must_change_password: true` and issues a **fully privileged access token anyway**.
No permission class, middleware or view checks the flag. A new hire holding only the emailed
temporary password can call every endpoint indefinitely and never rotate it. Enforcement exists
purely as a frontend redirect, which is bypassed by calling the API directly.

Compounded by V-11: temporary passwords come from `random` (not `secrets`) with only 10
alphanumeric characters and no rate limiting (V-19).

**Fix:** A global DRF permission that rejects every request except `change-password` and `logout`
while the flag is set.

---

### V-17 — HR can delete the company owner
**PoC:** `V17HRPrivilegeCreep` · **Location:** `backend/accounts/views.py:30-49`

The `scope=non_admin` query parameter is gated to `ADMIN`:

```python
if scope == "non_admin":
    if user.role != "ADMIN":
        raise PermissionDenied("Permission denied")
```

…but the **default** queryset applies no such filter, so an HR user simply omits the parameter
and receives every user in the tenant, including `ADMIN` rows. The same queryset backs
`EmployeeDetailAPIView`, so HR can `DELETE` the company owner — which via V-16 is a permanent
deletion of the owner and all their records.

Throughout the codebase `ADMIN` and `HR` are treated as interchangeable (`_is_payroll_manager`,
and every `role not in ["ADMIN", "HR"]` check), so HR also sets salaries, runs payroll, credits
payments, and edits company config.

**Fix:** A real permission matrix. HR must never be able to read, modify or delete `ADMIN`
accounts, and destructive/financial actions belong to `ADMIN` only.

---

### V-19 — No rate limiting anywhere, including login
**PoC:** `V19NoLoginRateLimit` · **Location:** `backend/core/settings.py:189-193`

`REST_FRAMEWORK` configures only `DEFAULT_AUTHENTICATION_CLASSES`. There is no
`DEFAULT_THROTTLE_CLASSES`, no `django-axes`, no lockout, no CAPTCHA, no failed-attempt logging.
50 consecutive failed logins were all processed normally.

Login IDs are **enumerable and predictable** (V-11): `OI` + initials + year + a global 4-digit
serial. An attacker can generate the entire valid login-id space for a target year and
brute-force it, against 10-character temporary passwords that were never required to change
(V-15).

**Fix:** DRF scoped throttles on auth endpoints, plus per-account lockout with exponential
backoff and alerting.

---

### V-20 — Re-running payroll erases the payment audit trail
**PoC:** `V20PayrollRerunErasesPaymentAudit` · **Location:** `backend/payroll/views.py:200-218`

```python
if not created:
    if payroll.status == "PAID":
        payroll.status = "PENDING"
        payroll.credited_at = None
        payroll.credited_by = None
```

`POST /api/payroll/run/` with no arguments defaults to the current month and processes **every**
employee. If any payslip for that month was already credited, the run silently reverts it to
`PENDING` and discards `credited_at`/`credited_by`. There is no confirmation prompt, no flag
requirement, and no record that money was already paid.

The operator then sees the payslip as unpaid and pays it a second time.

**Fix:** Never mutate a `PAID` record. Recomputation must create a superseding revision and
require an explicit, audited override.

---

### V-27 — No password reset, and passwords are transmitted to be forgotten
**Location:** `backend/auth_api/urls.py`, `backend/accounts/urls.py`

There is no forgot-password endpoint, no email verification, and no email backend configured at
all (`EMAIL_BACKEND` is absent from `settings.py`). The only password-change path requires the
current password.

Employee onboarding therefore depends on an admin reading a generated temporary password off the
API response (`auth_api/views.py:75-79`) and relaying it out-of-band. A user who forgets their
password has **no recovery route** and must ask an admin to delete and recreate them — which via
V-16 destroys their payroll history.

**Fix:** Signed, expiring, single-use reset tokens delivered by email; email verification at
signup; an invitation flow that never puts a password in an API response.

---

## Medium

### V-04 — Check-out crashes with a 500 when there is no check-in
**PoC:** `V04CheckoutCrash` · **Location:** `backend/attendance/views.py:36-41`

```python
delta = attendance.check_out - attendance.check_in   # check_in may be None
```

`check_in` is `null=True`, and V-06's leave approval creates rows with `check_in=None`. The
subtraction raises `TypeError` → unhandled 500. Reachable by any authenticated employee.

**Fix:** Guard for a missing check-in and return 400.

---

### V-05 — Leave requests accept reversed and unbounded date ranges
**PoC:** `V05LeaveDateValidation` · **Location:** `backend/leave/views.py:13-40`, `backend/leave/serializers.py`

No validation that `end_date >= start_date`, no maximum duration, no bound on how far into the
past or future a request may reach, and no leave-balance/quota system despite the README
advertising one. A ten-year leave request is accepted. A reversed range is accepted and then
makes the overlap check in `ApplyLeaveAPIView` behave incorrectly.

Approving a long range also drives the unbounded `while current <= leave.end_date` loop in
`leave/views.py:104-111`, writing one `Attendance` row per day — a decade-long request writes
~3,650 rows in a single request cycle. That is a denial-of-service vector.

**Fix:** Validate ordering, cap duration, restrict backdating, and add a real leave-balance model.

---

### V-08 — Payroll can compute a negative net salary
**PoC:** `V08NegativeNetSalary` · **Location:** `backend/payroll/views.py:77-97`

```python
net_salary = quantize_currency(base_net_salary - expense_to_pay)
```

Nothing clamps the result. The PoC produced a net salary of **-49000.00**. There is no floor, no
deduction cap, and no validation that `outstanding` is recoverable from a single month's pay.
`PayrollCreditAPIView` will happily mark a negative payslip as `PAID`.

Related: `monthly_salary` permits `0.00` and there is no upper bound, so `daily_rate` can be zero
or absurd; and `EmployeeSalary.monthly_salary` duplicates `CustomUser.salary`, giving two
divergent sources of truth for the same fact.

**Fix:** Clamp net pay at zero, carry the remainder forward as outstanding, cap per-period
deductions, and drop the duplicated `CustomUser.salary` column.

---

### V-11 — Login IDs are predictable, globally sequential, and racy
**PoC:** `V11LoginIdCollision` · **Location:** `backend/accounts/utils.py:7-19`

```python
count = CustomUser.objects.filter(date_of_joining__year=year).count() + 1
```

The counter is **global across every tenant**, not per-company. Confirmed: tenant A's first hire
gets `...0001` and an unrelated tenant B's first hire gets `...0002`. Each customer's login IDs
therefore leak the platform-wide employee count — a direct business-metrics disclosure to every
competitor who signs up.

`COUNT()+1` is also read-modify-write with no lock or uniqueness retry. Two concurrent hires
compute the identical ID (confirmed: `OISAPO20300002 == OISAPO20300002`); one insert then fails
with an `IntegrityError` 500 on the unique constraint.

`generate_temp_password` uses `random.choices` — the Mersenne Twister PRNG, **not
cryptographically secure** — for 10 characters of credential material.

**Fix:** Per-organization sequence or a random opaque identifier; `secrets` for anything
credential-shaped; a retry loop around the unique constraint.

---

### V-12 — Refresh tokens are accepted as WebSocket credentials
**PoC:** `V12RefreshTokenAuthenticatesWebSocket` · **Location:** `backend/realtime/auth.py:11-25`

```python
validated_token = UntypedToken(raw_token)
```

`UntypedToken` deliberately skips the `token_type` claim check, so a 7-day refresh token
authenticates a WebSocket exactly like a 1-day access token — confirmed by the PoC.

The token is also passed in the **query string** (`?token=...`), where it lands in access logs,
proxy logs, and browser history.

**Fix:** Validate with `AccessToken`, and move the credential to the `Sec-WebSocket-Protocol`
header or a short-lived single-use ticket.

---

### V-14 — Django 4.2 is past end-of-life and breaks on the installed Python
**Location:** `backend/requirements.txt:1`

`Django==4.2` reached end of extended support in **April 2026** — four months before this audit.
It receives no further security patches.

It is also incompatible with the Python 3.14 installed on this machine. Django 4.2's
`BaseContext.__copy__` calls `super().__copy__()`, which raises on 3.14:

```
AttributeError: 'super' object has no attribute 'dicts' and no __dict__ for setting new attributes
```

This fires inside Django's **own 500 error handler**, so any server error triggers a second
crash while trying to report the first — errors become undiagnosable in production.

Also pinned: `djangorestframework==3.14.0` and `dj-database-url==0.5.0`, both several years old.

**Fix:** Upgrade to Django 5.2 LTS and refresh the dependency set.

---

### V-18 — The employee directory exposes every colleague's salary
**PoC:** `V18SalaryExposedInDirectory` · **Location:** `backend/accounts/serializers.py:52-69`

`EmployeeListSerializer` includes `salary` and is used for the list endpoint. Any `ADMIN` or `HR`
user receives every employee's salary in the directory payload, and it is written into the
`/api/accounts/employees/export/` spreadsheet. There is no field-level permission and no
distinction between "may manage people" and "may see compensation".

**Fix:** Remove `salary` from the directory serializer; serve compensation only from the payroll
endpoints under an explicit permission.

---

### V-22 — Insecure defaults across production settings
**Location:** `backend/core/settings.py`

| Line | Setting | Problem |
|---|---|---|
| 29 | `SECRET_KEY` | Falls back to `"django-insecure-change-me"` — a known constant that forges session cookies and password-reset tokens |
| 36 | `DEBUG` | Defaults to **`True`**; must be explicitly disabled, and it also gates the V-03 backdoor |
| 88 | `CORS_ALLOW_ALL_ORIGINS` | `True` — every origin on the internet may call the API |
| — | `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER` | All absent |
| 111-115 | `CHANNEL_LAYERS` | `InMemoryChannelLayer` — documented as unsuitable for production; realtime updates break silently with more than one worker process |
| — | `LOGGING` | Not configured at all — no application logs |

Secure-by-default requires the opposite polarity: fail closed unless production explicitly opts
out.

---

### V-23 — JWTs in `localStorage`, no rotation, no revocation
**Location:** `frontend/src/contexts/AuthContext.tsx:53`, `backend/core/settings.py:195-199`

```js
localStorage.setItem('dayflow_auth_tokens', JSON.stringify({access, refresh}));
```

* `localStorage` is readable by any script on the origin — V-09 turns an XSS into full account
  takeover.
* `ACCESS_TOKEN_LIFETIME` is **1 day** (typical: 5-15 minutes).
* `ROTATE_REFRESH_TOKENS` and `BLACKLIST_AFTER_ROTATION` are unset, and
  `token_blacklist` is not installed — so **logout revokes nothing**. `logout()` clears
  `localStorage` client-side while the token stays valid server-side for up to 7 days.
* No `/api/auth/refresh/` route is wired up at all (the README documents one), so the frontend
  never refreshes — the session simply dies after 24 hours.

**Fix:** Short-lived access tokens, refresh-token rotation with blacklisting, refresh in an
httpOnly `Secure` `SameSite` cookie, and a real logout that blacklists.

---

### V-24 — Authorization is enforced in the UI, not the API
**Location:** `frontend/src/App.tsx:47-60`, `frontend/src/components/layout/DashboardLayout.tsx`

`DashboardLayout` checks only `isAuthenticated`, and `isAuthenticated` derives from
`localStorage.dayflow_user` — a value the user controls. **No route checks `role`.** Admin
routes (`/dashboard/admin`, `/payroll`, `/employees/admin`) render for any logged-in user.

Editing `localStorage.dayflow_user` to `{"role":"ADMIN"}` reveals the entire admin UI. The
backend does re-check roles on most endpoints, so this leaks interface rather than data — but
`/api/dashboard/employee/`, `/api/attendance/*` and `/api/leave/apply/` have **no role check at
all**, so an `ADMIN` is treated as an employee there and vice versa.

**Fix:** Server-authoritative role from a `/api/auth/me/` endpoint, plus a `<RequireRole>` route
guard. Treat the frontend as untrusted.

---

### V-26 — Naive timezone handling corrupts attendance at day boundaries
**Location:** `attendance/views.py:17,74`, `dashboard/views.py:16,59,213`, `payroll/views.py:33`

`USE_TZ = True` and `TIME_ZONE = "UTC"`, but the code mixes `timezone.now()` (aware, UTC) with
`date.today()` (**the server's local date**). On a server not set to UTC these disagree for part
of every day.

There is also no per-organization timezone. Every tenant's working day is defined by the
server's clock, so an employee in Mumbai checking in at 09:00 IST is recorded against the
previous UTC day — corrupting the `unique_together("user", "date")` day boundary, the dashboard's
"today", and the monthly attendance counts that drive payroll.

**Fix:** `timezone.localdate()` throughout, an `Organization.timezone` field, and day boundaries
computed in the organization's timezone.

---

### V-30 — No audit log for any privileged or financial action
**Location:** codebase-wide

Salary changes, payroll runs, salary credits, leave approvals, employee deletion, and company
config changes leave no audit trail. `PayrollRecord` records `generated_by`/`credited_by`, but
V-20 nulls those out on re-run. Nothing records *who* changed a salary, *when*, or *from what*.

The README claims an "audit-ready mindset" and lists "Audit logs" as a future enhancement — for a
system holding payroll data this is a compliance requirement, not an enhancement.

**Fix:** An append-only `AuditLog` model written for every privileged mutation.

---

## Low

### V-21 — `force_recompute` is accepted and silently ignored
**PoC:** `V21ForceRecomputeIgnored` · **Location:** `backend/payroll/views.py:171`

The flag is declared in `PayrollRunSerializer`, parsed into a local variable, and then never
read. Callers relying on it get behaviour that does not match the API contract.

### V-25 — Company config can orphan users' roles and departments
**Location:** `backend/accounts/views.py:211-254`, `backend/accounts/serializers.py:72-136`

`PUT /api/accounts/company-config/` replaces `departments`/`roles`/`employment_types` wholesale
with no check that existing users still reference the removed values. Employees are left with a
`department` string that no longer exists in config, and `CreateEmployeeSerializer.validate_role`
then rejects role values that current employees already hold.

### V-28 — `AllAttendance` and `AllLeaves` exclude ADMIN and cannot be filtered
**Location:** `attendance/views.py:63-67`, `leave/views.py:62-66`

Both endpoints `.exclude(user__role="ADMIN")`, so an admin's own attendance is invisible to the
company and admins are exempt from oversight. Neither endpoint accepts a date range, and neither
is paginated — they return **every attendance row ever recorded** for the tenant on every page
load, alongside a WebSocket that triggers a refetch on every database change.

### V-29 — No pagination on any list endpoint
**Location:** codebase-wide

`REST_FRAMEWORK` sets no `DEFAULT_PAGINATION_CLASS`. `/api/accounts/employees/`,
`/api/attendance/all/`, `/api/leave/all/`, `/api/payroll/records/` and `/api/payroll/salaries/`
all return unbounded result sets.

### V-31 — Electron opens DevTools in production builds
**Location:** `frontend/electron/main.cjs:61`

```js
mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
mainWindow.webContents.openDevTools();   // <- production branch
```

DevTools open on every launch of the shipped desktop app. The `will-navigate` guard on line 67
also only allows `file://` and `http://localhost:8080`, so it does not reflect the real
production origin.

### V-32 — Vite dev proxy disables TLS certificate verification
**Location:** `frontend/vite.config.ts:16,21`

`secure: false` on both the `/api` and `/ws` proxies disables certificate validation against the
production backend, making developer machines trivially machine-in-the-middle-able.

### V-33 — No Content-Security-Policy
**Location:** `frontend/index.html`, `backend/core/settings.py`

No CSP is set by either the SPA or the API. Combined with V-09 (stored XSS) and V-23 (tokens in
`localStorage`), there is nothing to prevent an injected script from exfiltrating credentials to
an arbitrary host.

### V-34 — Repository hygiene
**Location:** repository root

* `backend/core/settings.py:31-33` — **live Razorpay API keys committed in plaintext** to a
  public repository. `RAZORPAY_KEY_SECRET = "BbwMnLgv3liaosjUbw5uXBO2"`. These must be treated as
  compromised and rotated regardless of any other fix.
* `backend/db.sqlite3` is tracked in Git.
* `backend/.env.example` is empty, so no one can tell what configuration is required.
* Compiled `__pycache__/*.pyc` files were tracked and committed.
* `frontend/release/` (packaged Electron binaries) and `frontend/local_cache/` (a 101 MB Electron
  download) were untracked but sitting in the working tree; both are now ignored.

---

## Fix status

Tracked in [`docs/FIX_LOG.md`](./FIX_LOG.md), updated as each remediation commit lands.

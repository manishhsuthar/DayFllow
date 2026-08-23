# DayFlow — Remediation Log

Tracks every finding from [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) from discovery to fix.

**Legend:** 🔴 Open · 🟡 In progress · 🟢 Fixed & regression-tested

| ID | Severity | Finding | Status | Fixed in | Regression test |
|---|---|---|---|---|---|
| V-01 | Critical | Unauthenticated tenant takeover via public registration | 🟢 Fixed | tenancy | `V01TenantTakeover` |
| V-02 | High | Registration leaks full Python traceback | 🟢 Fixed | security baseline | `V02RegistrationLeaksTraceback` |
| V-03 | Critical | Hardcoded credential backdoor mints a superuser | 🟢 Fixed | security baseline | `V03LoginBackdoor` |
| V-04 | Medium | Check-out 500s when there is no check-in | 🟢 Fixed | attendance/leave | `V04CheckoutCrash` |
| V-05 | Medium | Leave accepts reversed / unbounded date ranges | 🟢 Fixed | attendance/leave | `V05LeaveDateValidation` |
| V-06 | High | Leave approval destroys attendance history | 🟢 Fixed | attendance/leave | `V06LeaveApprovalDestroysAttendance` |
| V-07 | High | Employees post unlimited expenses against own salary | 🟢 Fixed | payroll/audit | `V07EmployeeSelfExpense` |
| V-08 | Medium | Payroll can compute a negative net salary | 🟢 Fixed | payroll/audit | `V08NegativeNetSalary` |
| V-09 | High | Stored XSS in the HTML salary slip | 🟢 Fixed | tenancy | `V09SlipXSS` |
| V-10 | Critical | Payment grants no entitlement; verify is unauthenticated | 🔴 Open | — | `V10PaymentGrantsNothing` |
| V-11 | Medium | Login IDs predictable, globally sequential, racy | 🟢 Fixed | tenancy | `V11LoginIdCollision` |
| V-12 | Medium | Refresh tokens accepted as WebSocket credentials | 🔴 Open | — | `V12RefreshTokenAuthenticatesWebSocket` |
| V-13 | Critical | Postgres-only raw SQL; silently defaults to SQLite | 🟢 Fixed | tenancy | — |
| V-14 | Medium | Django 4.2 is EOL and breaks on Python 3.14 | 🟢 Fixed | security baseline | — |
| V-15 | High | `must_change_password` never enforced | 🟢 Fixed | security baseline | `V15MustChangePasswordBypass` |
| V-16 | Critical | "Soft delete" is a hard delete of financial records | 🟢 Fixed | tenancy | `V16HardDeleteDestroysPayrollHistory` |
| V-17 | High | HR can delete the company owner | 🟢 Fixed | tenancy | `V17HRPrivilegeCreep` |
| V-18 | Medium | Employee directory exposes salaries | 🟢 Fixed | tenancy | `V18SalaryExposedInDirectory` |
| V-19 | High | No rate limiting, including on login | 🟢 Fixed | security baseline | `V19NoLoginRateLimit` |
| V-20 | High | Payroll re-run erases the payment audit trail | 🟢 Fixed | payroll/audit | `V20PayrollRerunErasesPaymentAudit` |
| V-21 | Low | `force_recompute` accepted and ignored | 🟢 Fixed | payroll/audit | `V21ForceRecomputeIgnored` |
| V-22 | Medium | Insecure production defaults | 🟢 Fixed | security baseline | — |
| V-23 | Medium | JWTs in localStorage; no rotation or revocation | 🔴 Open | — | — |
| V-24 | Medium | Authorization enforced in UI, not API | 🔴 Open | — | — |
| V-25 | Low | Company config can orphan roles and departments | 🟢 Fixed | tenancy | — |
| V-26 | Medium | Naive timezone handling corrupts day boundaries | 🟢 Fixed | attendance/leave | `V26TimezoneHandling` |
| V-27 | High | No password reset; no email backend | 🟢 Fixed | tenancy | — |
| V-28 | Low | `AllAttendance`/`AllLeaves` exclude ADMIN, unfiltered | 🟢 Fixed | attendance/leave | `V28UnboundedHistoryQueries` |
| V-29 | Low | No pagination on any list endpoint | 🟢 Fixed | security baseline | — |
| V-30 | Medium | No audit log for privileged or financial actions | 🟢 Fixed | payroll/audit | `V30AuditTrail` |
| V-31 | Low | Electron opens DevTools in production builds | 🔴 Open | — | — |
| V-32 | Low | Vite dev proxy disables TLS verification | 🔴 Open | — | — |
| V-33 | Low | No Content-Security-Policy | 🔴 Open | — | — |
| V-34 | Low | Repository hygiene; committed Razorpay secret | 🟡 Partial | security baseline | — |

## Progress

| | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Open | 1 | 0 | 3 | 2 | **6** |
| Partial | 0 | 0 | 0 | 1 | **1** |
| Fixed | 4 | 9 | 9 | 5 | **27** |

### payroll/audit — money and accountability

Fixed V-07, V-08, V-20, V-21, V-30.

- **Expenses are claims now.** `POST /salaries/add-expense/` only checked for a payroll manager
  when an `employee_id` was supplied, so any employee could omit it and move an unlimited,
  unreviewable, irreversible amount against their own pay. `ExpenseClaim` has
  PENDING/APPROVED/REJECTED, only approval touches `outstanding`, nobody reviews their own claim,
  and a claim cannot be reviewed twice.
- **Net pay is floored at zero**, in code and by a database `CheckConstraint`. Recovery of
  outstanding expenses is capped at half of gross and the remainder is recorded in
  `expense_carried_forward` rather than driving the payslip negative (the audit reproduced
  −49000.00). Migration `payroll.0005` clamps any existing negative rows into carry-forward
  before the constraint lands.
- **A credited payslip is immutable.** Re-running payroll used to reset PAID records to PENDING
  and discard `credited_at`/`credited_by`, so an operator saw an unpaid payslip and paid it
  twice. Re-runs now report skipped records with a reason, and not even `force_recompute` will
  touch a PAID one.
- `force_recompute` is honoured: without it a pending payslip is left alone, with it the record
  is recomputed and its `revision` incremented.
- **An append-only `AuditLog`** records salary changes (with before/after), payroll runs,
  credits, expense decisions, leave decisions, employee create/deactivate/reactivate and settings
  changes. Entries are written in the same transaction as the action, refuse to be updated or
  deleted, and are readable at `GET /api/audit/` by the organization owner only.
- Salaries are USD-only; setting a salary and crediting payroll are owner-only actions.

### attendance/leave — domain correctness

Fixed V-04, V-05, V-06, V-26, V-28.

- **Approving leave can no longer destroy worked days.** It used to `update_or_create` the whole
  range to `LEAVE`, leaving rows that claimed both `LEAVE` and nine hours worked — and since
  payroll pays on `PRESENT` days, an approved leave request silently cut pay for days the
  employee was at work. Applying over a day with a recorded check-in is now refused up front,
  approval over one returns 409, and a legitimate approval clears the time fields instead of
  leaving stale ones behind.
- **Leave ranges are validated**: end on or after start, at most 90 days, at most 30 days
  backdated, at most a year ahead, and a non-empty reason. The unbounded
  `while current <= end_date` loop that wrote one attendance row per day could previously be
  driven ~3,650 iterations by a single request.
- Nobody approves their own leave, and a decided request cannot be decided twice.
- **Check-out no longer 500s** when `check_in` is `NULL` — the exact state approved leave creates.
  Check-in/check-out now run under `select_for_update`.
- **The working day comes from `Organization.timezone`**, not `date.today()` on the server. The
  old code mixed server-local dates with UTC timestamps, so the two disagreed for part of every
  day and neither matched the employee's actual working day.
- History endpoints are bounded (90-day default, 366-day maximum), filterable by employee,
  status and date range, and paginated. Admins are no longer excluded from attendance oversight.

### tenancy — a real Organization model

Fixed V-01, V-09, V-11, V-13, V-16, V-17, V-18, V-25, V-27.

- **`Organization` replaces the `company_name` string.** Every tenant-scoped query now filters
  on a foreign key. Signup *creates* an organization and can never join one: a name whose slug is
  already taken is refused, so the unauthenticated takeover in V-01 is closed at the root.
  `organizations/scoping.py` centralises the filter so it cannot be forgotten per-view, and a
  user with no organization gets a 403 rather than falling through to an unscoped queryset.
- Data migrations `accounts.0012`–`0014` convert existing tenants, fold `CompanyConfig` and
  `CompanyLogo` into `Organization`, move `CustomUser.salary` into `payroll.EmployeeSalary`
  (they were two divergent records of the same fact), and only then drop the legacy columns.
  Slug-equivalent names merge rather than splitting a customer in half; blank company names are
  left unlinked rather than being dropped into an arbitrary tenant.
- **`company_table_service.py` is deleted.** It issued `CREATE TABLE` per customer using
  Postgres-only DDL, which made signup fail outright on the documented SQLite setup — and no
  query in the codebase ever read those tables.
- **Deletion is now deactivation.** The old `perform_destroy` deleted the employee's payroll
  records first, specifically to get around the `on_delete=PROTECT` guarding them. Records are
  retained; the owner and the caller's own account cannot be deactivated at all.
- **ADMIN and HR are no longer interchangeable.** HR cannot see, manage or deactivate an ADMIN,
  cannot change company settings, and cannot mint another HR account.
- Salary is out of the employee directory and its export; the payroll endpoints serve it.
- Login ids come from a per-organization `SELECT FOR UPDATE` sequence instead of a global
  `COUNT()+1`, so they no longer leak the platform-wide employee count or collide under
  concurrency. Temporary passwords use `secrets`, not the Mersenne Twister.
- The HTML salary slip is a Django template with autoescaping and its own restrictive CSP;
  `logo_url` must be an absolute `https://` URL.
- Self-service password reset over signed, expiring, single-use tokens, with identical responses
  for known and unknown emails. Plus `/api/auth/me/`, `/api/auth/logout/` (which blacklists) and
  `/api/auth/refresh/`.
- Company settings can no longer drop a role or department that active employees still hold.

### security baseline — `backend` settings, dependencies, auth

Fixed V-02, V-03, V-14, V-15, V-19, V-22, V-29; partially V-34.

- Django 4.2 (EOL, and crashes on Python 3.14 inside its own error handler) → **Django 5.2 LTS**;
  DRF, SimpleJWT, `dj-database-url` and psycopg refreshed alongside it.
- `settings.py` rewritten to **fail closed**. `DEBUG` now defaults to `False`; a missing
  `SECRET_KEY`, `ALLOWED_HOSTS`, CORS allowlist, database or Redis raises `ImproperlyConfigured`
  at boot instead of falling back to an insecure default. `CORS_ALLOW_ALL_ORIGINS = True`
  is replaced by an explicit origin allowlist. HSTS, SSL redirect, secure cookies, nosniff,
  `X-Frame-Options: DENY` and the proxy TLS header are all set when `DEBUG` is off.
- The **hardcoded `admin1@gmail.com` / `adminisadmin` backdoor is deleted**, along with the
  `create_superuser` call it used to conjure an account out of a failed login.
- `must_change_password` is enforced in a custom authentication class
  (`accounts/authentication.py`), not a permission class — DRF discards
  `DEFAULT_PERMISSION_CLASSES` for any view that sets its own, and nearly every view here does.
  Only change-password, refresh, logout and `me` stay reachable during a pending rotation.
- Scoped throttles on login, signup, password reset, billing and export.
- A project-wide DRF exception handler logs faults with a correlation id and returns an opaque
  error; the registration endpoint no longer returns a Python traceback.
- Argon2 password hashing; 15-minute access tokens (was 1 day) with refresh rotation and
  blacklisting, so logout can actually revoke.
- Default pagination on every list endpoint.
- Hardcoded Razorpay keys removed from `settings.py`; `db.sqlite3` and committed `.pyc` files
  untracked; `.env.example` filled in.

**V-34 remains partial:** the Razorpay keys are still in Git history and must be rotated.

---

## Action required outside the codebase

- **Rotate the Razorpay API keys** committed in `backend/core/settings.py` (V-34). They are in
  public Git history; removing them from the working tree does not un-publish them.
- **Rotate `DJANGO_SECRET_KEY`** on the deployed environment if it was ever the
  `django-insecure-change-me` default (V-22).
- **Audit the production database for rogue ADMIN accounts** created via V-01 before the fix
  lands. Check `accounts_customuser` for multiple `role='ADMIN'` rows sharing a `company_name`.

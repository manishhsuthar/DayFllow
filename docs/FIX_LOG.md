# DayFlow — Remediation Log

Tracks every finding from [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) from discovery to fix.

**Legend:** 🔴 Open · 🟡 In progress · 🟢 Fixed & regression-tested

| ID | Severity | Finding | Status | Fixed in | Regression test |
|---|---|---|---|---|---|
| V-01 | Critical | Unauthenticated tenant takeover via public registration | 🔴 Open | — | `V01TenantTakeover` |
| V-02 | High | Registration leaks full Python traceback | 🟢 Fixed | security baseline | `V02RegistrationLeaksTraceback` |
| V-03 | Critical | Hardcoded credential backdoor mints a superuser | 🟢 Fixed | security baseline | `V03LoginBackdoor` |
| V-04 | Medium | Check-out 500s when there is no check-in | 🔴 Open | — | `V04CheckoutCrash` |
| V-05 | Medium | Leave accepts reversed / unbounded date ranges | 🔴 Open | — | `V05LeaveDateValidation` |
| V-06 | High | Leave approval destroys attendance history | 🔴 Open | — | `V06LeaveApprovalDestroysAttendance` |
| V-07 | High | Employees post unlimited expenses against own salary | 🔴 Open | — | `V07EmployeeSelfExpense` |
| V-08 | Medium | Payroll can compute a negative net salary | 🔴 Open | — | `V08NegativeNetSalary` |
| V-09 | High | Stored XSS in the HTML salary slip | 🔴 Open | — | `V09SlipXSS` |
| V-10 | Critical | Payment grants no entitlement; verify is unauthenticated | 🔴 Open | — | `V10PaymentGrantsNothing` |
| V-11 | Medium | Login IDs predictable, globally sequential, racy | 🔴 Open | — | `V11LoginIdCollision` |
| V-12 | Medium | Refresh tokens accepted as WebSocket credentials | 🔴 Open | — | `V12RefreshTokenAuthenticatesWebSocket` |
| V-13 | Critical | Postgres-only raw SQL; silently defaults to SQLite | 🔴 Open | — | — |
| V-14 | Medium | Django 4.2 is EOL and breaks on Python 3.14 | 🟢 Fixed | security baseline | — |
| V-15 | High | `must_change_password` never enforced | 🟢 Fixed | security baseline | `V15MustChangePasswordBypass` |
| V-16 | Critical | "Soft delete" is a hard delete of financial records | 🔴 Open | — | `V16HardDeleteDestroysPayrollHistory` |
| V-17 | High | HR can delete the company owner | 🔴 Open | — | `V17HRPrivilegeCreep` |
| V-18 | Medium | Employee directory exposes salaries | 🔴 Open | — | `V18SalaryExposedInDirectory` |
| V-19 | High | No rate limiting, including on login | 🟢 Fixed | security baseline | `V19NoLoginRateLimit` |
| V-20 | High | Payroll re-run erases the payment audit trail | 🔴 Open | — | `V20PayrollRerunErasesPaymentAudit` |
| V-21 | Low | `force_recompute` accepted and ignored | 🔴 Open | — | `V21ForceRecomputeIgnored` |
| V-22 | Medium | Insecure production defaults | 🟢 Fixed | security baseline | — |
| V-23 | Medium | JWTs in localStorage; no rotation or revocation | 🔴 Open | — | — |
| V-24 | Medium | Authorization enforced in UI, not API | 🔴 Open | — | — |
| V-25 | Low | Company config can orphan roles and departments | 🔴 Open | — | — |
| V-26 | Medium | Naive timezone handling corrupts day boundaries | 🔴 Open | — | — |
| V-27 | High | No password reset; no email backend | 🔴 Open | — | — |
| V-28 | Low | `AllAttendance`/`AllLeaves` exclude ADMIN, unfiltered | 🔴 Open | — | — |
| V-29 | Low | No pagination on any list endpoint | 🟢 Fixed | security baseline | — |
| V-30 | Medium | No audit log for privileged or financial actions | 🔴 Open | — | — |
| V-31 | Low | Electron opens DevTools in production builds | 🔴 Open | — | — |
| V-32 | Low | Vite dev proxy disables TLS verification | 🔴 Open | — | — |
| V-33 | Low | No Content-Security-Policy | 🔴 Open | — | — |
| V-34 | Low | Repository hygiene; committed Razorpay secret | 🟡 Partial | security baseline | — |

## Progress

| | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Open | 4 | 6 | 10 | 6 | **26** |
| Partial | 0 | 0 | 0 | 1 | **1** |
| Fixed | 1 | 3 | 2 | 1 | **7** |

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

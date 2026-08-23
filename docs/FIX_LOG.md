# DayFlow — Remediation Log

Tracks every finding from [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md) from discovery to fix.

**Legend:** 🔴 Open · 🟡 In progress · 🟢 Fixed & regression-tested

| ID | Severity | Finding | Status | Fixed in | Regression test |
|---|---|---|---|---|---|
| V-01 | Critical | Unauthenticated tenant takeover via public registration | 🔴 Open | — | `V01TenantTakeover` |
| V-02 | High | Registration leaks full Python traceback | 🔴 Open | — | `V02RegistrationLeaksTraceback` |
| V-03 | Critical | Hardcoded credential backdoor mints a superuser | 🔴 Open | — | `V03LoginBackdoor` |
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
| V-14 | Medium | Django 4.2 is EOL and breaks on Python 3.14 | 🔴 Open | — | — |
| V-15 | High | `must_change_password` never enforced | 🔴 Open | — | `V15MustChangePasswordBypass` |
| V-16 | Critical | "Soft delete" is a hard delete of financial records | 🔴 Open | — | `V16HardDeleteDestroysPayrollHistory` |
| V-17 | High | HR can delete the company owner | 🔴 Open | — | `V17HRPrivilegeCreep` |
| V-18 | Medium | Employee directory exposes salaries | 🔴 Open | — | `V18SalaryExposedInDirectory` |
| V-19 | High | No rate limiting, including on login | 🔴 Open | — | `V19NoLoginRateLimit` |
| V-20 | High | Payroll re-run erases the payment audit trail | 🔴 Open | — | `V20PayrollRerunErasesPaymentAudit` |
| V-21 | Low | `force_recompute` accepted and ignored | 🔴 Open | — | `V21ForceRecomputeIgnored` |
| V-22 | Medium | Insecure production defaults | 🔴 Open | — | — |
| V-23 | Medium | JWTs in localStorage; no rotation or revocation | 🔴 Open | — | — |
| V-24 | Medium | Authorization enforced in UI, not API | 🔴 Open | — | — |
| V-25 | Low | Company config can orphan roles and departments | 🔴 Open | — | — |
| V-26 | Medium | Naive timezone handling corrupts day boundaries | 🔴 Open | — | — |
| V-27 | High | No password reset; no email backend | 🔴 Open | — | — |
| V-28 | Low | `AllAttendance`/`AllLeaves` exclude ADMIN, unfiltered | 🔴 Open | — | — |
| V-29 | Low | No pagination on any list endpoint | 🔴 Open | — | — |
| V-30 | Medium | No audit log for privileged or financial actions | 🔴 Open | — | — |
| V-31 | Low | Electron opens DevTools in production builds | 🔴 Open | — | — |
| V-32 | Low | Vite dev proxy disables TLS verification | 🔴 Open | — | — |
| V-33 | Low | No Content-Security-Policy | 🔴 Open | — | — |
| V-34 | Low | Repository hygiene; committed Razorpay secret | 🔴 Open | — | — |

## Progress

| | Critical | High | Medium | Low | Total |
|---|---|---|---|---|---|
| Open | 5 | 9 | 12 | 8 | **34** |
| Fixed | 0 | 0 | 0 | 0 | **0** |

---

## Action required outside the codebase

- **Rotate the Razorpay API keys** committed in `backend/core/settings.py` (V-34). They are in
  public Git history; removing them from the working tree does not un-publish them.
- **Rotate `DJANGO_SECRET_KEY`** on the deployed environment if it was ever the
  `django-insecure-change-me` default (V-22).
- **Audit the production database for rogue ADMIN accounts** created via V-01 before the fix
  lands. Check `accounts_customuser` for multiple `role='ADMIN'` rows sharing a `company_name`.

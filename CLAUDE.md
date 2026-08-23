# CLAUDE.md

Guidance for Claude Code working in this repository.

## What this is

DayFlow: a multi-tenant HR SaaS (attendance, leave, payroll, expenses) billed in
USD through Stripe. Django 5.2 + DRF + Channels on the backend, React 18 + Vite +
TypeScript on the frontend, with an optional Electron shell.

This branch (`prod`) is a security-driven rebuild of an earlier hackathon
codebase. A full review found 34 defects; all are fixed and covered by regression
tests. Read [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md) before making
security-adjacent changes — much of the current design exists because of a
specific defect, and the reasoning is not always obvious from the code alone.

## Commands

```bash
make setup            # venv + npm install
make migrate seed     # schema + default USD plans
make backend          # API  -> :8000
make frontend         # SPA  -> :8080
make test             # 124 backend tests + frontend typecheck
make audit            # the security regression suite alone
make check            # Django checks + deployment checklist
make help             # everything else
```

Tests use `core/settings_test.py` automatically and blank `DATABASE_URL`, so they
can never reach a real database. **`backend/.env` points at a production
Postgres** — never run `manage.py` against it without overriding `DATABASE_URL`.

## Non-negotiables

These are all defects that were found in production code here. Breaking one
reintroduces a known vulnerability.

1. **Every tenant-scoped query filters on `Organization`.** Use
   `organizations.scoping.organization_of(user)`. Never compare company names.
2. **Cross-tenant lookups return 404, not 403.** A 403 confirms the record exists.
3. **ADMIN ≠ HR.** HR manages people. ADMIN moves money and changes settings.
   `accounts/permissions.py` holds the matrix; `can_manage_target` does per-object
   checks.
4. **Never trust the client about payment.** Subscription state changes only in
   the signature-verified Stripe webhook handler.
5. **Money is `Decimal` or integer cents.** Never float. Net pay is floored at
   zero, in code and by a database constraint.
6. **Deleting an employee deactivates them.** Payroll records are retained.
7. **Dates come from `Organization.timezone`** via `attendance.views.workday_for`,
   never `date.today()`.
8. **Privileged actions call `audit.services.record()`** inside the same
   transaction.
9. **Settings fail closed.** Do not add a fallback that lets production boot
   without a secret key, host list, CORS allowlist, database or Redis.
10. **Never return a traceback to a client.** `core/exceptions.py` logs with a
    correlation id and returns an opaque error.

## Layout

```
backend/
  core/            settings, urls, ASGI, pagination, exception handler
  core/tests_poc.py  security regression suite — one class per audit finding
  organizations/   Organization + scoping helpers    ← the tenant boundary
  accounts/        users, roles, permissions, signup, directory
  auth_api/        login, logout, refresh, me, password reset, hiring
  attendance/  leave/  payroll/  billing/  audit/  realtime/
frontend/src/
  api/             one module per backend area; client.ts owns auth + refresh
  contexts/AuthContext.tsx     server-authoritative identity
  components/auth/RequireAuth.tsx   role-aware route guards
  pages/
```

## Testing conventions

`core/tests_poc.py` is one class per audit finding. A docstring saying **FIXED**
asserts the secure behaviour; one without it demonstrates a live defect.

When fixing a finding, **invert its test rather than deleting it** — that test is
the proof the fix works and the alarm if it regresses. Then update the row in
`docs/FIX_LOG.md`.

## Gotchas

- **`DEFAULT_PERMISSION_CLASSES` does not apply** to any view that declares its
  own `permission_classes`, and nearly every view here does. That is why password
  rotation is enforced in an authentication class, not a permission class.
- **`SimpleRateThrottle.THROTTLE_RATES` is a class attribute bound at import**, so
  `override_settings(REST_FRAMEWORK=...)` cannot reach it. Patch the class.
- **`swappable_dependency(AUTH_USER_MODEL)` resolves to `accounts.__first__`**,
  where the model is still called `User`. Depend on a concrete migration.
- **Adding a `CheckConstraint` fails if existing rows violate it.** Clean the data
  in a preceding migration (see `payroll.0005` → `0006`).
- **Audit `changes` values are nested** as `{"field": {"from": x, "to": y}}`;
  `_jsonable` recurses, because `x` is routinely a Decimal or datetime.
- **Vite inlines `VITE_*` at build time.** Changing the API origin needs a
  rebuild, and anything in a `VITE_` variable is public.
- **List endpoints are paginated.** Frontend calls go through `unwrapList`.

## Documentation

| File | Covers |
|---|---|
| `docs/ARCHITECTURE.md` | Tenancy, data model, request lifecycle, decisions |
| `docs/API.md` | Every endpoint |
| `docs/CONFIGURATION.md` | Every environment variable |
| `docs/BILLING.md` | Stripe setup and troubleshooting |
| `docs/DEPLOYMENT.md` | Production deployment + pre-launch checklist |
| `docs/OPERATIONS.md` | Runbook |
| `docs/CONTRIBUTING.md` | Conventions and workflow |
| `docs/SECURITY_AUDIT.md` | All 34 findings with reproductions |
| `docs/FIX_LOG.md` | Remediation status |

Keep `docs/API.md` current when you change an endpoint, and `docs/FIX_LOG.md`
current when you close a finding.

## Outstanding

**The Razorpay API keys committed in the old `settings.py` are in Git history and
must be rotated in the Razorpay dashboard.** Removing them from the working tree
does not un-publish them. This cannot be fixed from the codebase — see
`docs/FIX_LOG.md`.

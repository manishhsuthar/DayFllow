# Architecture

How DayFlow is put together, and why. Where a decision exists to close an audit
finding, the finding is cited — those are in
[`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md).

---

## 1. Tenancy

**One `Organization` row per customer. Every tenant-scoped query filters on it.**

This is the single most important thing in the codebase. Tenancy used to be a
free-text `company_name` field on the user, compared with
`filter(company_name=request.user.company_name)`. Because signup accepted an
arbitrary company name and auto-promoted the account to `ADMIN`, anyone could
type an existing customer's name and take over their tenant (V-01).

```
Organization
  ├─ name, slug (unique), timezone
  ├─ departments[], roles[], employment_types[], logo_url
  ├─ bypass_attendance
  ├─ owner            -> CustomUser
  ├─ employee_sequence  (per-tenant login-id counter)
  └─ members          <- CustomUser.organization
```

Three rules hold it together:

1. **Signup creates a tenant; it can never join one.** A name whose slug is
   already taken is refused, including slug-equivalent spellings
   (`Acme Corp` / `acme corp` / `ACME-CORP`). Joining an existing organization
   happens by invitation from its admin.
2. **Scoping goes through one helper.** `organizations/scoping.py` exposes
   `organization_of(user)` and `scope_to_organization(qs, user, path)`. The same
   forgotten-filter bug appeared in five apps; centralising it makes the filter
   hard to omit.
3. **No organization means no data.** A user with `organization = NULL` — a
   platform superuser from `createsuperuser` — gets a 403, never a fall-through
   to an unscoped queryset.

### Why a FK and not a schema or database per tenant

Row-level tenancy with a mandatory FK is the right size for this product. Schema-
per-tenant multiplies migration cost by the customer count; database-per-tenant
multiplies operational cost. The previous code actually attempted a table-per-
tenant scheme (`CREATE TABLE company_<slug>` from user input) which was
unmigratable, invisible to the ORM, Postgres-only, and never read by a single
query (V-13). It is gone.

### Timezones

`Organization.timezone` is an IANA name, and `organization.today()` resolves the
working day in it. The old code mixed `timezone.now()` (UTC) with `date.today()`
(the server's local date), so the two disagreed for part of every day and neither
matched the employee's actual working day (V-26).

---

## 2. Data model

```
Organization ──1:N── CustomUser ──1:1── EmployeeSalary
     │                   │                    │
     │                   ├──1:N── Attendance  └──1:N── PayrollRecord
     │                   ├──1:N── LeaveRequest
     │                   └──1:N── ExpenseClaim
     │
     ├──1:1── Subscription ──N:1── Plan
     └──1:N── AuditLog
```

Notes that are easy to get wrong:

- **`CustomUser.login_id` is the username field**, not email. Login accepts
  either; the serializer resolves an email to its login id first.
- **There is no `CustomUser.salary`.** It used to exist alongside
  `EmployeeSalary.monthly_salary` with nothing keeping them in step, so the
  directory reported one number while payroll paid another (V-08, V-18).
  `EmployeeSalary` is the only source of truth, and `accounts.0013` migrated the
  old column into it before dropping it.
- **`PayrollRecord.net_salary` has a `CheckConstraint` forbidding negatives.**
  Nothing floored the calculation before, so outstanding expenses could push a
  payslip to −49000.00 and the credit endpoint would mark it PAID (V-08).
- **Deleting an employee sets `is_active = False`.** The old `perform_destroy`
  deleted their `EmployeeSalary` and every `PayrollRecord` first — including PAID
  ones — specifically to defeat the `on_delete=PROTECT` guarding them (V-16).
- **`AuditLog` refuses `save()` on an existing row and refuses `delete()`.**

---

## 3. Request lifecycle

```
Request
  │
  ├─ CorsMiddleware              explicit origin allowlist, no wildcard
  ├─ SecurityMiddleware          HSTS, SSL redirect, nosniff
  ├─ WhiteNoiseMiddleware        static files
  ├─ Session / CSRF / Auth       Django defaults
  │
  ├─ DayFlowJWTAuthentication    ← validates the token AND enforces
  │                                must_change_password
  ├─ Permission classes          IsAuthenticated (default, fail closed)
  │                              IsManagement / IsOrganizationOwner
  │                              HasActiveSubscription / HasSeatAvailable
  ├─ ScopedRateThrottle          login, signup, password reset, billing, export
  │
  ├─ View                       queryset scoped via organization_of(user)
  │
  └─ core.exceptions.exception_handler
                                 logs with a correlation id, returns an opaque
                                 error — never a traceback (V-02)
```

### Why password rotation is enforced in *authentication*

`must_change_password` used to be advisory: login returned the flag and issued a
fully privileged token anyway, with enforcement living only in a frontend
redirect that calling the API directly bypassed (V-15).

It is enforced in `accounts/authentication.py`, not a permission class, because
**DRF replaces `DEFAULT_PERMISSION_CLASSES` wholesale for any view that declares
its own `permission_classes`** — and nearly every view here does. A default
permission would have silently not applied. Authentication always runs.

Only `change-password`, `refresh`, `logout` and `me` stay reachable while a
rotation is pending.

---

## 4. Authorization

Three roles, and they are genuinely different. Everything used to be
`role not in ["ADMIN", "HR"]`, so HR could set salaries, run payroll, credit
payments, edit settings — and delete the company owner (V-17).

| Capability | ADMIN | HR | EMP / INT |
|---|:--:|:--:|:--:|
| See the employee directory | ✅ | ✅ (no ADMIN rows) | ❌ |
| Create an employee | ✅ | ✅ (not HR accounts) | ❌ |
| Deactivate an employee | ✅ | ✅ (not an ADMIN) | ❌ |
| Approve leave | ✅ | ✅ | ❌ |
| Review expense claims | ✅ | ✅ (not their own) | ❌ |
| **Set salaries** | ✅ | ❌ | ❌ |
| **Credit payroll** | ✅ | ❌ | ❌ |
| **Change company settings** | ✅ | ❌ | ❌ |
| **Billing and plan changes** | ✅ | ❌ | ❌ |
| **Read the audit trail** | ✅ | ❌ | ❌ |
| Own attendance, leave, expenses | ✅ | ✅ | ✅ |

`accounts/permissions.py` holds `IsManagement`, `IsOrganizationOwner` and
`can_manage_target(actor, target)`, which is what stops HR acting on an ADMIN and
anyone acting across tenants.

The frontend has matching guards (`RequireAuth`, `RoleGate`). Those are **defence
in depth, not the boundary** — they exist so people are not shown screens whose
every request would 403.

---

## 5. Billing

**Stripe is the source of truth. The local `Subscription` row is a cache.**

The browser can ask for a Checkout session. It can never report what was paid —
that arrives by signature-verified webhook. The old flow had an unauthenticated
`verify/` endpoint that returned success and wrote nothing at all (V-10).

```
Browser                 API                     Stripe
   │                     │                        │
   │ POST /billing/checkout/                      │
   ├────────────────────►│                        │
   │                     │ create Checkout session│
   │                     ├───────────────────────►│
   │ 302 to Stripe       │◄───────────────────────┤
   │◄────────────────────┤                        │
   │                                              │
   │ ─────────── pays on Stripe's page ──────────►│
   │                                              │
   │                     │  webhook (signed)      │
   │                     │◄───────────────────────┤
   │                     │  verify → apply → audit│
   │ redirect back       │                        │
   │◄────────────────────┤                        │
```

- **Idempotency.** `WebhookEvent` records every event id. Stripe retries on any
  non-2xx and can deliver the same event twice; a duplicate is acknowledged and
  ignored. A handler fault returns 500, so Stripe retries.
- **Unknown statuses fail closed.** A Stripe status not in `STATUS_MAP` maps to
  `incomplete` and is logged, so a status we have never seen cannot silently
  become an entitlement.
- **Money is integer cents.** Floats do not represent currency.
- **Card details never reach this server.** Checkout and the portal are
  Stripe-hosted.

Entitlement (`billing/permissions.py`) is deliberately narrow: `SAFE_METHODS`
always pass. A lapsed customer can read and export everything and reach billing;
what closes is creating new work. `past_due` stays entitled — a failed card
should prompt someone, not lock them out of payroll the same day.

---

## 6. Realtime

`realtime/signals.py` broadcasts model changes to a per-organization channel
group; the SPA debounces and refetches.

- The group name is `sha256(organization_id)[:32]`, so it carries no tenant data.
- Credentials are validated with `AccessToken`, **not** `UntypedToken`, which
  skips the `token_type` claim and accepted seven-day refresh tokens (V-12).
- The credential travels in `Sec-WebSocket-Protocol`, falling back to the query
  string only because browsers cannot set headers on a WebSocket handshake.
- `channels-redis` is required in production; the in-memory layer only works with
  exactly one worker process and fails silently otherwise.

---

## 7. Configuration

`core/settings.py` **fails closed**. With `DJANGO_DEBUG` off, a missing secret
key, allowed-hosts list, CORS allowlist, database or Redis raises
`ImproperlyConfigured` at boot rather than falling back to something insecure.
`DEBUG` itself defaults to `False`; it used to default to `True`, which also
armed a hardcoded login backdoor (V-03, V-22).

Tests get their own module, `core/settings_test.py`, selected automatically by
`manage.py test`, so production settings can stay strict without making the test
suite require a wall of environment variables. It also blanks `DATABASE_URL` so
the suite can never reach a real database.

Full reference: [`CONFIGURATION.md`](./CONFIGURATION.md).

---

## 8. Where things live

```
backend/
  core/            settings, urls, ASGI, pagination, exception handler, tests_poc
  organizations/   Organization, scoping helpers          ← the tenant boundary
  accounts/        CustomUser, permissions, signup, directory, settings
  auth_api/        login, logout, refresh, me, password reset, employee creation
  attendance/      check-in / check-out, history
  leave/           requests and approvals
  payroll/         salaries, runs, credits, slips, expense claims
  billing/         Plan, Subscription, Stripe gateway, webhooks, entitlement
  audit/           append-only AuditLog
  realtime/        Channels consumer, auth, broadcast signals
  templates/       server-rendered salary slip (autoescaped)

frontend/src/
  api/             one module per backend area; client.ts holds auth + refresh
  contexts/        AuthContext — server-authoritative identity
  components/auth/ RequireAuth, RoleGate
  components/      layout, billing, shadcn/ui primitives
  pages/           one per route
```

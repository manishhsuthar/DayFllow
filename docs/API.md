# API Reference

Base path `/api`. All request and response bodies are JSON.

---

## Conventions

**Authentication.** `Authorization: Bearer <access_token>`. Access tokens last
15 minutes; refresh tokens 7 days, rotated on every refresh and blacklisted after
rotation. A 401 means refresh; a failed refresh means log in again.

**Tenancy.** Every authenticated endpoint is scoped to the caller's organization.
There is no cross-tenant access, and asking for another tenant's record returns
**404**, not 403 — a 403 would confirm the record exists.

**Pagination.** List endpoints return an envelope:

```json
{ "count": 137, "next": "...?page=2", "previous": null, "results": [ ... ] }
```

`?page=` and `?page_size=` (max 200) control it.

**Errors.**

```json
{ "detail": "Human-readable message" }                     // most failures
{ "field_name": ["Message about this field."] }            // validation
{ "detail": "An unexpected error occurred...", "error_id": "a1b2c3d4e5f6" }
```

`error_id` correlates with the server log. Tracebacks are never returned.

| Status | Means |
|---|---|
| 400 | Validation failed |
| 401 | Missing or expired access token — refresh |
| 402 | Seat limit reached — upgrade the plan |
| 403 | Authenticated but not permitted, or a password rotation is pending |
| 404 | Not found, or not yours |
| 409 | Conflicts with existing data (e.g. leave over a worked day) |
| 429 | Rate limited |
| 503 | Billing is not configured on this deployment |

**Password rotation.** While `must_change_password` is set, every endpoint
returns `403` with `code: "password_rotation_required"` except
`/auth/change-password/`, `/auth/refresh/`, `/auth/logout/` and `/auth/me/`.

**Rate limits.** login `10/min`, signup `5/hour`, password reset `5/hour`,
billing `30/min`, export `10/hour`. All configurable — see
[CONFIGURATION.md](./CONFIGURATION.md).

---

## Authentication

### `POST /api/auth/login/` · public · throttled

```json
{ "login_id": "ada@northwind.test", "password": "..." }
```

`login_id` accepts a login id or an email address.

```json
{
  "access": "eyJ...",
  "refresh": "eyJ...",
  "must_change_password": false,
  "user": {
    "id": 1, "login_id": "NORTHWIN-OWNER", "email": "ada@northwind.test",
    "first_name": "Ada", "last_name": "Lovelace",
    "role": "ADMIN", "department": "", "employment_type": "",
    "date_of_joining": "2026-08-23", "must_change_password": false,
    "organization": {
      "name": "Northwind Traders", "slug": "northwind-traders",
      "timezone": "Europe/London", "logo_url": ""
    }
  }
}
```

Failures return `400` with the same message for every cause, so the endpoint
cannot distinguish "no such account" from "wrong password".

### `POST /api/auth/refresh/` · public

`{ "refresh": "..." }` → `{ "access": "...", "refresh": "..." }`

Rotation is on: the old refresh token is blacklisted. Use the new one.

### `POST /api/auth/logout/` · authenticated

`{ "refresh": "..." }` → `{ "detail": "Logged out." }`

Blacklists the refresh token server-side. Clearing client storage alone leaves
the session live for up to a week.

### `GET /api/auth/me/` · authenticated

Returns the `user` object above. **This is the authority on the caller's role.**

### `POST /api/auth/change-password/` · authenticated

```json
{ "old_password": "...", "new_password": "..." }
```

Returns `{ "detail": ..., "access": ..., "refresh": ..., "user": {...} }` — a
fresh session, so the caller is not left holding a token minted under the old
password.

### `POST /api/auth/password-reset/` · public · throttled

`{ "email": "..." }` → `{ "detail": "If that email is registered, a reset link has been sent." }`

The response is identical for known and unknown addresses, so the endpoint cannot
enumerate accounts.

### `POST /api/auth/password-reset/confirm/` · public · throttled

`{ "uid": "...", "token": "...", "new_password": "..." }`

Tokens are signed, expire after an hour, and are single-use.

---

## Organizations

### `POST /api/accounts/register/` · public · throttled

Creates a **new** company and its owner. It cannot join an existing one.

```json
{
  "first_name": "Ada", "last_name": "Lovelace",
  "email": "ada@northwind.test", "password": "...",
  "company_name": "Northwind Traders",
  "timezone": "Europe/London"
}
```

→ `201`

```json
{
  "message": "Company created successfully.",
  "login_id": "NORTHWIN-OWNER",
  "email": "ada@northwind.test",
  "organization": { "name": "...", "slug": "northwind-traders", "timezone": "Europe/London" }
}
```

A company name whose slug is taken returns `400`, including slug-equivalent
spellings. The owner starts on a 14-day trial. `timezone` is an IANA name and
defaults to `UTC`.

### `GET /api/accounts/company-config/` · ADMIN, HR
### `PUT /api/accounts/company-config/` · ADMIN

```json
{
  "name": "Northwind Traders", "slug": "northwind-traders",
  "timezone": "Europe/London", "logo_url": "https://cdn.example.com/logo.png",
  "departments": ["Engineering", "Sales"],
  "roles": ["EMP", "INT", "HR"],
  "employment_types": ["Full-time", "Contract"],
  "bypass_attendance": false,
  "updated_at": "2026-08-23T10:00:00Z"
}
```

`PUT` is partial. It rejects removing a role or department that active employees
still hold, and `logo_url` must be an absolute `https://` URL.

`bypass_attendance` pays a full month regardless of recorded attendance.

---

## Employees

### `GET /api/accounts/employees/` · ADMIN, HR · paginated

Query: `scope=non_admin|employees_only`, `role=`, `include_inactive=true`.

HR never receives `ADMIN` rows. Deactivated employees are excluded unless
`include_inactive=true`. **No compensation data is returned** — use the payroll
endpoints.

### `POST /api/auth/create-employee/` · ADMIN, HR · needs an active subscription and a free seat

```json
{
  "first_name": "Grace", "last_name": "Hopper",
  "email": "grace@northwind.test", "role": "EMP",
  "date_of_joining": "2026-01-05",
  "department": "Engineering", "employment_type": "Full-time"
}
```

→ `201 { "login_id": "NORGRHO00001", "temporary_password": "…16 chars…", "message": "..." }`

The temporary password is shown **once**. Only ADMIN may create `HR` accounts.
Returns `403` when the subscription has lapsed or every seat is in use.

### `GET /api/accounts/employees/<id>/` · ADMIN, HR
### `DELETE /api/accounts/employees/<id>/` · ADMIN, HR

`DELETE` **deactivates**. Every payroll record is retained. Returns `204`.
The organization owner and the caller's own account cannot be deactivated.

### `POST /api/accounts/employees/<id>/reactivate/` · ADMIN, HR

Consumes a seat, exactly like hiring.

### `GET /api/accounts/employees/export/` · ADMIN, HR · throttled

An `.xlsx` file. No salary column.

---

## Attendance

History is bounded: a 90-day default window and a 366-day maximum. Pass
`start_date` / `end_date` (`YYYY-MM-DD`) to look further back. All day boundaries
resolve in the **organization's** timezone.

| Endpoint | Who | Notes |
|---|---|---|
| `POST /api/attendance/check-in/` | any | 400 if already checked in, or on approved leave |
| `POST /api/attendance/check-out/` | any | 400 if no check-in exists — never a 500 |
| `GET /api/attendance/my/` | any | paginated |
| `GET /api/attendance/all/` | ADMIN, HR | paginated; `employee_id`, `status`, date range |

Check-out returns `{ "detail", "check_out", "total_hours", "status" }`. Status
grades from hours: ≥8 `PRESENT`, ≥4 `HALF_DAY`, otherwise `ABSENT`.

---

## Leave

### `POST /api/leave/apply/` · any

```json
{ "leave_type": "CASUAL", "start_date": "2026-09-01", "end_date": "2026-09-03", "reason": "Family event" }
```

Types: `CASUAL`, `SICK`, `PAID`. Rejected when: `end_date` precedes
`start_date`; the range exceeds 90 days; it is backdated more than 30 days or
more than a year ahead; it overlaps an existing pending or approved request; or
**any day in the range has a recorded check-in**.

### `GET /api/leave/my/` · any · paginated · `?status=`
### `GET /api/leave/all/` · ADMIN, HR · paginated · `?status=`, `?employee_id=`

### `POST /api/leave/action/<id>/` · ADMIN, HR

`{ "action": "APPROVE" | "REJECT" }`

- `403` — nobody approves their own request; HR cannot act on an ADMIN's.
- `400` — the request was already decided.
- **`409`** — the range contains days the employee worked. Approving would
  overwrite them and cut pay for days they were present.

Approval writes one `LEAVE` attendance row per day and clears any stale
check-in / check-out / hours.

---

## Payroll

### `GET /api/payroll/salaries/`

ADMIN and HR get a list; an employee gets their own single record.

### `POST /api/payroll/salaries/` · **ADMIN only** · audited

`{ "employee_id": 12, "monthly_salary": "6200.00", "currency": "USD" }`

USD only. Salaries cannot be assigned to ADMIN accounts.

### `POST /api/payroll/run/` · ADMIN, HR

`{ "month": "2026-08", "employee_id": 12, "force_recompute": false }`

`month` defaults to the current month in the organization's timezone; a future
month is rejected.

```json
{
  "month": "2026-08",
  "results": [
    { "employee_id": 12, "employee_login_id": "NORGRHO00001", "status": "generated",
      "net_salary": "6200.00", "expense_carried_forward": "0.00", "revision": 1 }
  ],
  "skipped": [
    { "employee_id": 13, "employee_login_id": "NORJOSM00002",
      "reason": "already_paid", "credited_at": "2026-08-01T09:00:00Z" }
  ]
}
```

**A `PAID` payslip is never modified**, not even with `force_recompute` — it is
reported in `skipped` instead. Without the flag, an existing pending payslip is
also left alone (`already_generated`).

Calculation:

```
gross            = (monthly_salary / days_in_month) * (present + half_days/2)
deduction        = min(outstanding, gross * 0.50)     # capped at half of gross
net_salary       = gross - deduction                  # never below zero
carried_forward  = outstanding - deduction
```

### `GET /api/payroll/records/` · paginated

`?month=YYYY-MM`, `?status=PENDING|PAID`, `?employee_id=` (managers only).
Employees see only their own.

### `POST /api/payroll/records/<id>/credit/` · **ADMIN only** · audited

Marks a payslip paid and reduces the outstanding balance by the recovered amount.
Idempotent-by-refusal: a second call returns `400`.

### `GET /api/payroll/slips/<id>/` — JSON
### `GET /api/payroll/slips/<id>/html/?download=true` — printable HTML

Employees may read their own; managers may read any in their organization.
Rendered from an autoescaped template with its own restrictive CSP.

---

## Expenses

Submitting is a **request**. Only approval moves money.

### `POST /api/payroll/expenses/` · any

```json
{ "amount": "250.00", "description": "Client dinner", "incurred_on": "2026-08-01", "employee_id": 12 }
```

`employee_id` is optional and defaults to the caller; supplying someone else's
requires permission to manage them. The date cannot be in the future or more than
a year past.

### `GET /api/payroll/expenses/` · paginated · `?status=`, `?employee_id=`

Employees see their own; managers see the organization's.

### `POST /api/payroll/expenses/<id>/review/` · ADMIN, HR

`{ "action": "APPROVE" | "REJECT", "note": "optional" }`

Approval adds the amount to the employee's outstanding balance, recovered from
later payroll runs. **Nobody reviews their own claim** (403), and a claim cannot
be reviewed twice (400).

---

## Billing

### `GET /api/billing/plans/` · public

```json
{
  "currency": "usd", "trial_days": 14, "billing_enabled": true,
  "publishable_key": "pk_live_...",
  "plans": [
    { "code": "starter", "name": "Starter", "amount_cents": 1900, "amount": "19.00",
      "price_display": "$19.00", "currency": "usd", "interval": "month",
      "seat_limit": 10, "features": ["..."], "is_default": true }
  ]
}
```

`billing_enabled` is false when Stripe is unconfigured; checkout returns `503`.

### `GET /api/billing/subscription/` · authenticated

```json
{
  "status": "trialing", "plan": { ... }, "is_entitled": true,
  "seats_in_use": 7, "seat_limit": 10,
  "trial_end": "2026-09-06T00:00:00Z", "current_period_end": null,
  "cancel_at_period_end": false, "canceled_at": null
}
```

`is_entitled` is the single question the API asks. `trialing`, `active` and
`past_due` are entitled; `past_due` deliberately so, because a failed card should
prompt someone rather than lock them out of payroll the same day.

### `POST /api/billing/checkout/` · **ADMIN only** · throttled

`{ "plan_code": "growth" }` → `{ "checkout_url": "https://checkout.stripe.com/...", "session_id": "cs_..." }`

Redirect the browser to `checkout_url`. **The client never reports what was
paid** — that arrives by webhook.

### `POST /api/billing/portal/` · **ADMIN only** · throttled

`{ "return_url": "https://app.example.com/#/billing" }` → `{ "portal_url": "..." }`

Stripe's hosted portal: payment method, invoices, cancellation.

### `POST /api/billing/webhook/` · Stripe only

Requires a valid `Stripe-Signature`. Unauthenticated by necessity — Stripe cannot
hold a JWT — but a forged POST is rejected. Idempotent by event id.

Handled: `checkout.session.completed`, `customer.subscription.created|updated|deleted`,
`invoice.payment_succeeded|failed`. Anything else is acknowledged and ignored.

---

## Dashboard

| Endpoint | Who |
|---|---|
| `GET /api/dashboard/employee/` | any |
| `GET /api/dashboard/admin/` | ADMIN, HR |
| `GET /api/dashboard/notifications/` | any (content varies by role) |

---

## Audit

### `GET /api/audit/` · **ADMIN only** · paginated

`?action=`, `?actor=`

```json
{
  "id": 42, "action": "SALARY_SET", "action_label": "Salary set",
  "actor_label": "NORTHWIN-OWNER",
  "target_type": "CustomUser", "target_id": "12", "target_label": "NORGRHO00001",
  "changes": { "monthly_salary": { "from": "5000.00", "to": "6200.00" } },
  "created_at": "2026-08-23T10:15:00Z"
}
```

Append-only: entries cannot be edited or deleted, by anyone, including through
the Django admin.

Actions: `SALARY_SET`, `EXPENSE_SUBMITTED`, `EXPENSE_APPROVED`,
`EXPENSE_REJECTED`, `PAYROLL_RUN`, `PAYROLL_CREDITED`, `LEAVE_APPROVED`,
`LEAVE_REJECTED`, `EMPLOYEE_CREATED`, `EMPLOYEE_DEACTIVATED`,
`EMPLOYEE_REACTIVATED`, `SETTINGS_CHANGED`, `SUBSCRIPTION_CHANGED`.

---

## WebSocket

`wss://<api-host>/ws/updates/`

Authenticate with the `Sec-WebSocket-Protocol` header:

```js
new WebSocket(url, `dayflow.jwt.${accessToken}`);
```

`?token=<access>` also works, because browsers cannot set headers on a handshake,
but the subprotocol form keeps the credential out of access logs and history.

**Access tokens only** — refresh tokens are rejected. Close codes: `4401`
unauthenticated, `4403` no organization.

On connect: `{"type": "connected"}`. Then, for any change in your organization:

```json
{ "type": "data_changed", "model": "payroll.PayrollRecord",
  "action": "updated", "record_id": 42, "timestamp": "2026-08-23T10:15:00Z" }
```

The message carries no record contents — refetch what you need over HTTP, where
the same authorization applies.

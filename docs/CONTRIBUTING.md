# Contributing

## Setup

```bash
make setup          # venv + npm install, creates backend/.env
make migrate seed
make backend        # terminal 1 -> :8000
make frontend       # terminal 2 -> :8080
```

## Before you push

```bash
make test           # 124 backend tests + frontend typecheck
make audit          # security regressions specifically
make check          # Django checks + the deployment checklist
```

---

## The rules that matter

### 1. Every tenant-scoped query filters on the organization

Never write `Model.objects.filter(...)` on tenant data without it. Use the helper:

```python
from organizations.scoping import organization_of

queryset = Attendance.objects.filter(user__organization=organization_of(request.user))
```

`organization_of` raises `PermissionDenied` for a user with no organization,
rather than falling through to an unscoped queryset.

The same forgotten-filter bug appeared in five apps before the rewrite. If you
add a model that belongs to a tenant, add a test to `TenantIsolation` in
`core/tests_poc.py` proving one organization cannot see another's rows.

### 2. Cross-tenant lookups return 404, not 403

A 403 confirms the record exists. Filter by organization in the queryset and let
`get_object_or_404` do the rest.

### 3. Permissions are explicit

```python
from accounts.permissions import IsManagement, IsOrganizationOwner

class MyView(APIView):
    permission_classes = [IsAuthenticated, IsOrganizationOwner]
```

ADMIN and HR are **not** interchangeable. Money and settings are ADMIN only.
Use `can_manage_target(actor, target)` for per-object checks — it is what stops
HR acting on an ADMIN.

### 4. Privileged actions are audited

```python
from audit.models import AuditLog
from audit.services import record, diff

with transaction.atomic():
    before = {"monthly_salary": salary.monthly_salary}
    salary.monthly_salary = new_value
    salary.save()
    record(
        organization=employee.organization,
        actor=request.user,
        action=AuditLog.Action.SALARY_SET,
        target=employee,
        changes=diff(before, {"monthly_salary": new_value}),
    )
```

Inside the transaction, so an entry exists if and only if the action committed.

### 5. Dates come from the organization's timezone

```python
from attendance.views import workday_for

today = workday_for(request.user)      # not date.today()
```

`date.today()` is the *server's* local date and does not match the employee's
working day.

### 6. Money is Decimal, or integer cents

Never float. Plan prices are `amount_cents` integers; salaries and payslips are
`DecimalField`. Quantize with `quantize_currency` before storing.

### 7. Never trust the client about payment

The browser may request a Checkout session. Subscription state changes only in
`billing/api.py`'s webhook handler, after signature verification.

---

## Adding a tenant-scoped feature

1. **Model** — reach `Organization` through a FK, directly or via `user`/`employee`.
2. **Serializer** — never expose another tenant's identifiers.
3. **View** — scope the queryset; pick the right permission class.
4. **URL** — register under the app's `urls.py`.
5. **Realtime** — add the model to `WATCHED_MODELS` in `realtime/signals.py` if
   the UI should refetch on change.
6. **Audit** — call `record()` if the action is privileged or financial.
7. **Tests** — a happy path, a permission test, and a tenant-isolation test.
8. **Docs** — add the endpoint to `docs/API.md`.

---

## Tests

`backend/core/tests_poc.py` is organised **one class per audit finding**.

- A docstring saying **FIXED** asserts the secure behaviour. It must fail if the
  defect returns.
- One without it demonstrates a defect that is still open.

When you fix a finding, invert its test rather than deleting it. That test is the
proof the fix works, and the alarm if it regresses.

App-level tests (`accounts/tests.py`, `payroll/tests.py`) cover ordinary
behaviour.

---

## Migrations

- One logical change per migration, with a docstring explaining **why**.
- Data migrations need a reverse, or an explicit comment saying why they cannot
  have one (see `payroll/0005_clamp_negative_net_salary.py`).
- Never edit an applied migration. Add a new one.
- Adding a constraint to a table with violating rows fails: clean the data in a
  preceding migration (see `payroll.0005` → `0006`).
- Test both directions on a copy of production before deploying anything that
  drops a column.

---

## Code style

**Python** — 4 spaces, 100 columns, double quotes, `from __future__` not needed
on 3.11+. Type hints where they clarify.

**TypeScript** — 2 spaces, 100 columns, double quotes. Prefer `type` imports.
Components are function components with explicit prop types.

**Comments explain why, not what.** Where code exists to close an audit finding,
say so and cite it — that comment is what stops someone "simplifying" the fix
away:

```python
# AccessToken, not UntypedToken: this rejects refresh tokens (audit V-12).
```

Do not add comments restating the obvious. Match the density of the surrounding
code.

---

## Commits

```
type(scope): imperative summary under ~72 chars

Why the change was needed, and what it does about it. What broke, or
would have broken, without it. Reference the audit finding if there is one.

    make test   ->  124 tests, OK
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Mark an API-breaking
change with `!` and describe the break in the body.

One logical change per commit. A bug fix and a refactor in one commit is two
commits.

---

## Reporting a vulnerability

Do not open a public issue. Contact the maintainers directly with reproduction
steps. If you can write a failing test in `core/tests_poc.py`, include it.

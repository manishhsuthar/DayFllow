# Operations Runbook

For whoever is on call.

---

## Health

| Check | Endpoint | Expect |
|---|---|---|
| API alive | `GET /api/billing/plans/` | 200 — public, dependency-light |
| Database | `manage.py check --database default` | no output |
| Realtime | connect to `/ws/updates/` with an access token | `{"type":"connected"}` |

## Log streams

| Logger | Carries |
|---|---|
| `dayflow.audit` | Privileged and financial actions |
| `dayflow.billing` | Stripe calls, webhooks, subscription transitions |
| `dayflow.security` | Logins, password changes, resets |
| `django.request` | Unhandled errors, with the `error_id` returned to the client |

When a user reports an error, ask for the reference in the message — that is the
`error_id`, and it appears in `django.request`.

---

## Backups

Payroll data carries statutory retention requirements in most jurisdictions.

- Nightly automated Postgres backups, 30 days minimum.
- **Test the restore.** A backup you have never restored is a hypothesis.
- Redis needs no backup: it holds only channel-layer state.

```bash
pg_dump "$DATABASE_URL" --format=custom --file=dayflow-$(date +%F).dump
pg_restore --dbname="$TARGET_URL" --clean --if-exists dayflow-2026-08-23.dump
```

---

## Common incidents

### Subscriptions are not activating after payment

**Almost always the webhook.**

1. Stripe dashboard → Webhooks → your endpoint → recent deliveries. Are events
   being attempted? What status comes back?
2. `400` on every event → wrong `STRIPE_WEBHOOK_SECRET`. Each endpoint has its
   own; a `stripe listen` session has a different one again.
3. `500` on every event → read the stored error:
   ```sql
   SELECT stripe_event_id, event_type, error, received_at
   FROM billing_webhookevent
   WHERE processed_at IS NULL ORDER BY received_at DESC LIMIT 20;
   ```
4. No attempts at all → the endpoint URL is wrong or unreachable.

After fixing, replay the events from the Stripe dashboard. Processing is
idempotent, so replays are safe.

**Manual recovery for one customer**, if a webhook is lost for good:

```python
from billing.models import Subscription
from billing.services import apply_stripe_subscription
from billing import stripe_gateway

sub = Subscription.objects.get(organization__slug="acme-corp")
apply_stripe_subscription(sub, stripe_gateway.retrieve_subscription("sub_XXXX"))
```

This re-reads from Stripe rather than setting a status by hand. Never set
`status = "active"` directly — it will be overwritten by the next webhook and the
audit trail will show a change nobody made.

### A customer is locked out of creating records

Check entitlement first:

```python
from billing.services import get_or_create_subscription
from organizations.models import Organization

sub = get_or_create_subscription(Organization.objects.get(slug="acme-corp"))
print(sub.status, sub.is_entitled, sub.seats_in_use(), sub.seat_limit)
```

- `is_entitled` false → billing. Point them at the portal.
- Seats exhausted → they must upgrade or deactivate someone.
- Both fine → check for a pending password rotation on *their* account
  (`403 password_rotation_required`).

### Realtime updates stopped

- More than one worker without `REDIS_URL`. The in-memory channel layer cannot
  cross processes and fails **silently**.
- The reverse proxy is not passing `Upgrade`/`Connection` headers.
- The client is sending a refresh token: only access tokens authenticate a
  socket. Close code `4401`.

### Login is failing for everyone

- `DJANGO_SECRET_KEY` changed → every existing token is invalid. Users must log
  in again; there is no way around it.
- Throttled? `10/min` per IP by default. A whole office behind one NAT can trip
  it — raise `DJANGO_THROTTLE_LOGIN` or key throttling differently.
- `ImproperlyConfigured` at boot → read the message; it names the variable.

### Payroll numbers look wrong

Recompute is safe for pending payslips and refused for paid ones:

```bash
# Recompute one employee's pending payslip
curl -X POST .../api/payroll/run/ -H "Authorization: Bearer $TOKEN" \
  -d '{"month":"2026-08","employee_id":12,"force_recompute":true}'
```

Check first:

- **Attendance.** Payroll pays `PRESENT` days plus half of `HALF_DAY`. An
  employee who checks out immediately records 0 hours, which grades as `ABSENT`.
- **`bypass_attendance`.** If set on the organization, everyone is paid a full
  month regardless of attendance.
- **Expense recovery.** Deduction is capped at 50% of gross; the rest sits in
  `expense_carried_forward`. Net pay never goes negative.

A `PAID` payslip cannot be recomputed at all. If one is genuinely wrong, the
correct action is a documented adjustment in the next period — not editing a
record of money that already moved.

---

## Routine tasks

### Add a plan

Edit `DEFAULT_PLANS` in `backend/billing/management/commands/seed_plans.py`, then:

```bash
python manage.py seed_plans --sync-stripe
```

### Change a price

Create a **new** Stripe Price and point the plan at it. Stripe prices are
immutable; editing `amount_cents` alone makes the pricing page disagree with what
Stripe charges.

### Give a customer a longer trial

```python
from datetime import timedelta
from django.utils import timezone
from billing.models import Subscription

sub = Subscription.objects.get(organization__slug="acme-corp")
sub.trial_end = timezone.now() + timedelta(days=30)
sub.save(update_fields=["trial_end", "updated_at"])
```

Only valid while `status == "trialing"`. Once Stripe owns the subscription,
change the trial in Stripe so the two do not diverge.

### Investigate what someone did

```python
from audit.models import AuditLog
AuditLog.objects.filter(
    organization__slug="acme-corp", actor_label="ACMEHR001"
).values("created_at", "action", "target_label", "changes")[:50]
```

Or `GET /api/audit/?actor=ACMEHR001` as that organization's owner.

### Rotate the secret key

```bash
DJANGO_JWT_SIGNING_KEY=<old key>   # keep tokens valid
DJANGO_SECRET_KEY=<new key>        # rotate everything else
```

Then drop `DJANGO_JWT_SIGNING_KEY` after the refresh window (7 days by default)
to complete the rotation.

---

## Security response

**If a tenant reports data they do not recognise**, check for extra admins — the
signature of the old registration hole (audit V-01):

```sql
SELECT o.slug, u.login_id, u.email, u.created_at
FROM accounts_customuser u
JOIN organizations_organization o ON o.id = u.organization_id
WHERE u.role = 'ADMIN'
ORDER BY o.slug, u.created_at;
```

More than one ADMIN in an organization is legitimate, but any the customer does
not recognise — especially one created close to a data-access complaint — needs
investigating. Deactivate rather than delete: the audit trail is evidence.

**If a token is suspected leaked**, blacklist that user's outstanding tokens:

```python
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
for token in OutstandingToken.objects.filter(user__login_id="ACMEEMP001"):
    BlacklistedToken.objects.get_or_create(token=token)
```

**If the whole platform may be compromised**, rotate `DJANGO_SECRET_KEY` without
setting `DJANGO_JWT_SIGNING_KEY`. Every session dies immediately.

---

## Monitoring

Worth alerting on:

| Signal | Why |
|---|---|
| 5xx rate | The obvious one |
| Webhook failures (`WebhookEvent.processed_at IS NULL`, aging) | Silent revenue loss |
| Login 429 rate | Either an attack or a throttle set too low |
| Database connections | `CONN_MAX_AGE=600` holds connections open |
| Redis memory | Channel-layer growth |
| Certificate expiry | HSTS makes an expired certificate unrecoverable in-browser |

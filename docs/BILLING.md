# Billing — Stripe setup

DayFlow charges in **USD** through Stripe Checkout. This is everything needed to
go from a fresh Stripe account to taking money.

---

## The one rule

**Stripe is the source of truth. The browser is never believed.**

The client can ask for a Checkout session. It cannot tell the API what was paid —
that arrives by signature-verified webhook. This matters because the previous
implementation had an unauthenticated `verify/` endpoint that returned success
and wrote nothing to the database at all: paying granted nothing, and skipping
checkout cost nothing (audit V-10).

If webhooks are not delivered, **subscriptions never activate**, no matter how
many successful payments Stripe records. Webhook setup is not optional.

---

## 1. Get your keys

From <https://dashboard.stripe.com/apikeys>:

```bash
STRIPE_SECRET_KEY=sk_test_...          # sk_live_... in production
STRIPE_PUBLISHABLE_KEY=pk_test_...
```

Start in **test mode**. The dashboard's test/live toggle changes which keys you
see; test and live objects are entirely separate, including products and prices.

Put them in `backend/.env`. The secret key must never reach the frontend — the
publishable key is served by `GET /api/billing/plans/` so it can change without
a rebuild.

## 2. Create the products and prices

```bash
make seed                                        # local plan rows only
cd backend && .venv/bin/python manage.py seed_plans --sync-stripe
```

`--sync-stripe` creates a Stripe Product and a recurring USD Price for every plan
that has no `stripe_price_id`, and writes the id back. Re-running is safe: plans
already linked are skipped.

Default lineup (edit `backend/billing/management/commands/seed_plans.py`):

| Code | Name | Price | Seats |
|---|---|---|---|
| `starter` | Starter | $19 / month | 10 |
| `growth` | Growth | $49 / month | 50 |
| `enterprise` | Enterprise | $149 / month | unlimited |

**To change a price**, create a new Stripe Price and point the plan at it.
Editing `amount_cents` alone changes what the pricing page *says* while Stripe
still charges the old amount. Stripe prices are immutable by design.

## 3. Configure the webhook

<https://dashboard.stripe.com/webhooks> → **Add endpoint**

- **URL**: `https://<your-api-host>/api/billing/webhook/`
- **Events**:
  - `checkout.session.completed`
  - `customer.subscription.created`
  - `customer.subscription.updated`
  - `customer.subscription.deleted`
  - `invoice.payment_succeeded`
  - `invoice.payment_failed`

Copy the signing secret:

```bash
STRIPE_WEBHOOK_SECRET=whsec_...
```

Each endpoint has its **own** signing secret. Using the wrong one rejects every
event with a 400.

## 4. Set the return URLs

```bash
BILLING_SUCCESS_URL=https://app.dayflow.app/#/billing/success
BILLING_CANCEL_URL=https://app.dayflow.app/#/billing/cancelled
```

Note the `#/` — the SPA uses hash routing.

The success page **does not** activate the subscription; the webhook does. The
page refetches a few times over several seconds because the webhook can land
just after the redirect.

## 5. Enable the customer portal

<https://dashboard.stripe.com/settings/billing/portal> → activate, and allow
payment-method updates, invoice history, plan switching and cancellation.

Without this, `POST /api/billing/portal/` fails and customers cannot update a
failed card themselves.

---

## Testing locally

Forward events to your machine with the Stripe CLI:

```bash
stripe login
stripe listen --forward-to localhost:8000/api/billing/webhook/
```

`stripe listen` prints a **different** `whsec_...` for the forwarding session —
use that one locally.

Test cards (<https://stripe.com/docs/testing>):

| Card | Behaviour |
|---|---|
| `4242 4242 4242 4242` | Succeeds |
| `4000 0000 0000 9995` | Declined — insufficient funds |
| `4000 0000 0000 0341` | Attaches, then fails on charge → exercises `past_due` |
| `4000 0025 0000 3155` | Requires 3D Secure |

Any future expiry, any CVC, any postcode.

Trigger events directly:

```bash
stripe trigger checkout.session.completed
stripe trigger invoice.payment_failed
```

---

## How the pieces map

| DayFlow | Stripe |
|---|---|
| `Plan.stripe_price_id` | Price |
| `Subscription.stripe_customer_id` | Customer |
| `Subscription.stripe_subscription_id` | Subscription |
| `Subscription.status` | subscription status, via an explicit map |
| `WebhookEvent.stripe_event_id` | Event id, for idempotency |

`Organization.id` is written into Customer and Subscription metadata, so a
webhook can find the tenant even if local state is lost.

### Status and entitlement

| Stripe status | Entitled | Meaning |
|---|:--:|---|
| `trialing` | ✅ | Free trial, until `trial_end` |
| `active` | ✅ | Paid and current |
| `past_due` | ✅ | Payment failed, retries pending |
| `unpaid` | ❌ | Retries exhausted |
| `canceled` | ❌ | Ended |
| `incomplete` | ❌ | First payment never completed |
| `incomplete_expired` | ❌ | First payment abandoned |
| `paused` | ❌ | Paused collection |

`past_due` stays entitled on purpose: a failed card should prompt someone, not
lock them out of their own payroll the same day. The banner and the portal give
them a way to fix it.

**A status Stripe adds that we do not recognise maps to `incomplete` and is
logged** — an unknown status can never silently become an entitlement.

### What lapsing actually blocks

Narrow, by design:

- ✅ Still allowed: reading everything, exports, salary slips, billing, the portal
- ❌ Blocked: creating employees, reactivating employees

A customer whose card expired must still be able to see their payroll and fix
their card.

### Seats

A seat is an **active, non-admin** employee. Admins do not consume one.
Deactivating frees a seat immediately. Hiring past the limit returns `403` with
a message naming the plan and the limit.

---

## Going live

- [ ] Swap `sk_test_`/`pk_test_` for `sk_live_`/`pk_live_`
- [ ] Re-run `seed_plans --sync-stripe` — **live prices are different objects**
- [ ] Create a **live-mode** webhook endpoint and use its signing secret
- [ ] Activate the customer portal in live mode
- [ ] Confirm `BILLING_SUCCESS_URL` / `BILLING_CANCEL_URL` point at production
- [ ] Complete one real transaction and confirm the subscription activates
- [ ] Check `WebhookEvent` rows have `processed_at` set and `error` empty
- [ ] Set up Stripe email receipts and failed-payment notifications
- [ ] Configure tax if you are required to collect it (Stripe Tax)

---

## Troubleshooting

**Payment succeeded, subscription still `trialing`.** The webhook is not
arriving. Check the dashboard's webhook log for delivery attempts and response
codes, verify `STRIPE_WEBHOOK_SECRET` matches *that* endpoint, and confirm the
URL is publicly reachable.

**Every webhook returns 400.** Signature verification failed — almost always the
wrong signing secret, or middleware mutating the raw request body. The signature
is computed over the exact bytes.

**Checkout returns 503.** `STRIPE_SECRET_KEY` is unset.
`GET /api/billing/plans/` reports `billing_enabled: false`.

**"This plan is not connected to Stripe yet."** The plan has no
`stripe_price_id`. Run `seed_plans --sync-stripe`.

**The same event processed twice.** It should not be — `WebhookEvent` deduplicates
by event id. If you see it, check whether two deployments share a database but
have different webhook secrets.

**A webhook 500s repeatedly.** Read `WebhookEvent.error` for that event id.
Stripe retries with backoff for up to three days, so a transient fault
self-heals; a persistent one needs the underlying bug fixed and the event
replayed from the dashboard.

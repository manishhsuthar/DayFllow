# Configuration

Every setting comes from the environment. Copy `backend/.env.example` to
`backend/.env` and fill it in.

## Fail-closed

With `DJANGO_DEBUG` off, the app **refuses to start** unless the required values
are present. It raises `ImproperlyConfigured` at boot rather than falling back to
something insecure.

This is deliberate. The previous settings defaulted `DEBUG` to `True`, fell back
to a published `SECRET_KEY`, allowed every CORS origin, and silently downgraded
to SQLite when `DATABASE_URL` was missing — so a deployment could look healthy
while being wide open (audit V-22).

A boot failure names the variable and how to produce it. If the app will not
start, read the error: it is telling you exactly what is missing.

---

## Required in production

| Variable | Example | Why it is required |
|---|---|---|
| `DJANGO_SECRET_KEY` | *(50+ random chars)* | Signs sessions, password-reset tokens and JWTs. A known value forges all three. |
| `DJANGO_ALLOWED_HOSTS` | `api.dayflow.app` | Blocks Host-header attacks. Comma-separated. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `https://app.dayflow.app` | Exact frontend origins. There is no wildcard. |
| `DATABASE_URL` | `postgres://user:pw@host:5432/dayflow` | Postgres is required. |
| `REDIS_URL` | `redis://host:6379/0` | Channel layer. In-memory only works with one worker. |
| `STRIPE_SECRET_KEY` | `sk_live_…` | Billing. Opt out with `DJANGO_ALLOW_UNCONFIGURED_BILLING=true`. |
| `STRIPE_WEBHOOK_SECRET` | `whsec_…` | Verifies webhooks. Without it, subscription state never updates. |

Generate a secret key:

```bash
python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())'
```

---

## Core

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Never enable in production. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | *(the CORS list)* | Override only if they differ. |
| `DJANGO_ALLOW_DESKTOP_ORIGIN` | `false` | Allows `Origin: null` for the Electron build. Widens CORS to any local HTML file — enable only if you ship the desktop app. |
| `DJANGO_LOG_LEVEL` | `INFO` | |
| `DJANGO_PAGE_SIZE` | `50` | Default page size; `?page_size=` caps at 200. |
| `DJANGO_PASSWORD_MIN_LENGTH` | `10` | |

## Database

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | — | Preferred. Or use the discrete form below. |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` | — | All four of the first must be set together. |
| `DJANGO_DB_SSL_REQUIRE` | `true` unless `DEBUG` | Set `false` for a Postgres on a private network. |
| `DJANGO_DB_CONN_MAX_AGE` | `600` | Connection reuse, in seconds. |
| `DJANGO_ALLOW_SQLITE` | `false` | **Local development only.** |

## Realtime

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | — | Required unless `DEBUG`. |
| `DJANGO_ALLOW_INMEMORY_CHANNELS` | `false` | Only if you are certain you run exactly one worker. With more, some clients silently stop receiving updates. |

## Tokens

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_ACCESS_TOKEN_MINUTES` | `15` | Was 1 day. Shorter limits the blast radius of a leak. |
| `DJANGO_REFRESH_TOKEN_DAYS` | `7` | Rotated on refresh, blacklisted after. |
| `DJANGO_JWT_SIGNING_KEY` | *(the secret key)* | Set separately to rotate one without the other. |

## Billing

| Variable | Default | Notes |
|---|---|---|
| `STRIPE_SECRET_KEY` | — | `sk_test_…` or `sk_live_…` |
| `STRIPE_PUBLISHABLE_KEY` | — | Returned to the frontend. |
| `STRIPE_WEBHOOK_SECRET` | — | From the webhook endpoint in the dashboard. |
| `STRIPE_API_VERSION` | `2025-10-29.clover` | Pinned so a Stripe upgrade cannot change behaviour unannounced. |
| `BILLING_CURRENCY` | `usd` | |
| `BILLING_TRIAL_DAYS` | `14` | |
| `BILLING_SUCCESS_URL` | — | Where Checkout returns on success. |
| `BILLING_CANCEL_URL` | — | Where Checkout returns on cancel. |
| `DJANGO_ALLOW_UNCONFIGURED_BILLING` | `false` | Run without billing deliberately. |

See [BILLING.md](./BILLING.md) for the full Stripe setup.

## Email

Required for password reset and employee invitations. Without it the app starts,
but reset emails fail.

| Variable | Default |
|---|---|
| `DJANGO_EMAIL_BACKEND` | console in `DEBUG`, SMTP otherwise |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | — / `587` / — / — |
| `EMAIL_USE_TLS` | `true` |
| `DEFAULT_FROM_EMAIL` | `DayFlow <no-reply@dayflow.app>` |
| `FRONTEND_BASE_URL` | `http://localhost:8080` — reset links are built from this |
| `DJANGO_PASSWORD_RESET_TIMEOUT` | `3600` seconds |

## Rate limits

DRF rate strings (`<count>/<second|minute|hour|day>`).

| Variable | Default | Protects |
|---|---|---|
| `DJANGO_THROTTLE_LOGIN` | `10/min` | Password guessing |
| `DJANGO_THROTTLE_SIGNUP` | `5/hour` | Bulk tenant creation |
| `DJANGO_THROTTLE_PASSWORD_RESET` | `5/hour` | Reset-email flooding |
| `DJANGO_THROTTLE_BILLING` | `30/min` | Checkout-session churn |
| `DJANGO_THROTTLE_EXPORT` | `10/hour` | Bulk data extraction |

Throttling is in-process by default. Behind more than one worker, configure a
shared `CACHES` backend (Redis) or the limits apply per process.

## Transport

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECURE_SSL_REDIRECT` | `true` when not `DEBUG` | Set `false` only if something upstream already redirects. |
| `DJANGO_SECURE_HSTS_SECONDS` | `31536000` | Start lower when first enabling HSTS — it is hard to undo. |
| `DJANGO_BEHIND_TLS_PROXY` | `true` | Trusts `X-Forwarded-Proto`. **Only enable behind a proxy that overwrites it**, or a client can spoof HTTPS. |

---

## Frontend

Vite inlines these **at build time**, so changing one means rebuilding.

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | `/api` | Absolute URL when the API is on another origin. |
| `VITE_WS_URL` | `/ws/updates/` | Derived from the page origin when relative. |
| `VITE_DESKTOP_API_BASE_URL` | `http://localhost:8000/api` | Electron loads from `file://`, so a relative path has nothing to resolve against. |
| `VITE_PROXY_TARGET` | `http://localhost:8000` | Dev-server proxy target. |

Anything in a `VITE_`-prefixed variable **ships in the bundle and is public**.
Never put a secret in one. `STRIPE_PUBLISHABLE_KEY` is served by the API rather
than baked in, so it can change without a rebuild.

---

## Local development

`make backend` supplies safe local values:

```
DJANGO_DEBUG=true
DJANGO_ALLOW_SQLITE=true
DJANGO_SECRET_KEY=local-development-only
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:8080
DATABASE_URL=
```

`manage.py test` uses `core/settings_test.py`, which supplies its own values and
**blanks `DATABASE_URL`**, so the suite can never reach a real database.

---

## Verifying

```bash
make check                              # Django checks + the deployment checklist
cd backend && .venv/bin/python manage.py check --deploy
```

`--deploy` should report no issues with production settings loaded. If it
complains about `SECURE_HSTS_SECONDS` or `SESSION_COOKIE_SECURE`, `DEBUG` is
still on.

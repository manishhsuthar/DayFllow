# DayFlow

A multi-tenant HR platform — attendance, leave, payroll, expenses — sold as a
subscription in USD.

Each customer is an **Organization**: an isolated tenant with its own employees,
timezone, settings, billing and audit trail. New companies sign themselves up,
get a 14-day trial, and pay through Stripe Checkout.

---

## Status

This branch is a rebuild of an earlier hackathon codebase. Before the rebuild a
full security review found **34 defects**, five of them critical — including an
unauthenticated tenant takeover, a hardcoded login backdoor, and a paid tier that
granted nothing. All 34 are fixed and covered by regression tests that fail if
any of them return.

- Findings and reproductions: [`docs/SECURITY_AUDIT.md`](docs/SECURITY_AUDIT.md)
- Fix status per finding: [`docs/FIX_LOG.md`](docs/FIX_LOG.md)

```
make test          # 124 backend tests + frontend typecheck
make audit         # the security regression suite alone
```

**One thing is still outstanding and cannot be fixed from the codebase:** the
Razorpay API keys that were committed in plaintext are in Git history and must be
rotated in the Razorpay dashboard. See [`docs/FIX_LOG.md`](docs/FIX_LOG.md).

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| API | Django 5.2 LTS + DRF | 4.2 is end-of-life and breaks on Python 3.14 |
| Realtime | Channels + Redis | in-memory channels only work with one worker |
| Database | PostgreSQL 16 | required, not optional — SQLite must be opted into |
| Auth | SimpleJWT, 15-min access, rotating refresh | logout must actually revoke |
| Billing | Stripe Checkout + webhooks | Stripe is the source of truth, not the browser |
| Frontend | React 18, Vite, TypeScript, Tailwind, shadcn/ui | — |
| Desktop | Electron (optional) | packaged shell around the same SPA |

---

## Quick start

```bash
git clone <repository-url> && cd DayFllow
make setup                 # venv + npm install, and creates backend/.env
make migrate seed          # schema + the default USD plans
make superuser             # optional, for /admin
```

Then in two terminals:

```bash
make backend               # API -> http://localhost:8000
make frontend              # app -> http://localhost:8080
```

Open http://localhost:8080, click **Get Started**, and create a company. You are
its owner, on a 14-day trial.

Or run the whole stack, including Postgres and Redis:

```bash
make docker-up             # app -> http://localhost:8080
```

`make help` lists every command.

---

## How it fits together

```
                    ┌──────────────────┐
  Browser ────────► │  React SPA       │
  / Electron        │  (Vite, nginx)   │
                    └────────┬─────────┘
                             │ JWT over HTTPS  +  WebSocket
                    ┌────────▼─────────┐
                    │  Django + DRF    │◄──── Stripe webhooks
                    │  Channels (ASGI) │      (signature-verified)
                    └───┬─────────┬────┘
                        │         │
              ┌─────────▼──┐  ┌───▼────────┐
              │ PostgreSQL │  │  Redis     │
              └────────────┘  └────────────┘
```

Every tenant-scoped query filters on `Organization`. The full model and the
reasoning behind it is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Modules

**Organizations** — the tenant boundary. Name, slug, timezone, departments,
roles, employment types, logo. Signup *creates* one and can never join one.

**Accounts** — users, roles (`ADMIN`, `HR`, `EMP`, `INT`), invitations,
password reset. ADMIN and HR are genuinely different: HR manages people, ADMIN
moves money and changes settings.

**Attendance** — check-in and check-out, resolved against the organization's own
timezone. Hours grade to `PRESENT` / `HALF_DAY` / `ABSENT`.

**Leave** — casual, sick and paid leave with an approval workflow. Ranges are
bounded, and approval can never overwrite a day the employee actually worked.

**Payroll** — monthly runs from attendance, salary slips, credits. Net pay is
floored at zero; unrecovered expenses carry forward. A credited payslip is
immutable.

**Expenses** — claims with an approval workflow. Only approval moves money, and
nobody reviews their own claim.

**Billing** — plans, subscriptions, seat limits, Stripe Checkout and the customer
portal. Entitlement is enforced server-side.

**Audit** — an append-only record of every privileged and financial action, with
before/after values. Readable by the organization owner.

---

## Plans

| Plan | Price | Seats |
|---|---|---|
| Starter | $19 / month | 10 employees |
| Growth | $49 / month | 50 employees |
| Enterprise | $149 / month | Unlimited |

Every plan includes every feature — you are buying capacity and support, not
features. Seats count active non-admin employees; deactivating one frees it.
Edit `backend/billing/management/commands/seed_plans.py` to change the lineup.

A lapsed subscription blocks *creating new work*. It never blocks reading,
exporting, or reaching billing: a customer whose card expired must still be able
to see their payroll and fix their card.

---

## Documentation

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Tenancy model, data model, request lifecycle, design decisions |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | Every environment variable and what breaks without it |
| [API.md](docs/API.md) | Every endpoint, with request and response shapes |
| [BILLING.md](docs/BILLING.md) | Stripe setup, webhooks, testing checkout, going live |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production deployment and the pre-launch checklist |
| [OPERATIONS.md](docs/OPERATIONS.md) | Runbook: backups, incidents, common failures |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Conventions, workflow, how to add a tenant-scoped feature |
| [SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) | All 34 findings with reproductions |
| [FIX_LOG.md](docs/FIX_LOG.md) | Remediation status per finding |

---

## Testing

```bash
make test            # everything
make test-backend    # 124 Django tests
make audit           # security regressions only
make typecheck       # frontend types
make check           # Django checks + the deployment checklist
```

The security suite is organised one class per finding. A class whose docstring
says *FIXED* asserts the secure behaviour and fails if the defect returns.

---

## License

Developed for educational and hackathon purposes.

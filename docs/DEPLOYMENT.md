# Deployment

The API is an ASGI application (it serves WebSockets as well as HTTP), so it runs
under Daphne or Uvicorn — **not** under plain gunicorn WSGI workers.

---

## Requirements

| | Minimum | Notes |
|---|---|---|
| Python | 3.11 | Django 5.2 supports 3.10–3.14 |
| PostgreSQL | 14 | 16 recommended |
| Redis | 6 | Channel layer |
| Node | 20 | Frontend build only |
| TLS | required | HSTS and secure cookies are on by default |

---

## 1. Prepare the environment

```bash
cp backend/.env.example backend/.env
python -c 'from django.core.management.utils import get_random_secret_key as g; print(g())'
```

Fill in at minimum: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CORS_ALLOWED_ORIGINS`, `DATABASE_URL`, `REDIS_URL`,
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and the email settings.

Settings fail closed: if a required value is missing the app refuses to boot and
names it. See [CONFIGURATION.md](./CONFIGURATION.md).

## 2. Migrate and seed

```bash
python manage.py migrate --no-input
python manage.py seed_plans --sync-stripe
python manage.py collectstatic --no-input
python manage.py createsuperuser
```

Run migrations as a **release step**, before the new code serves traffic — not
from an app worker, or concurrent instances will race.

## 3. Run the API

```bash
daphne -b 0.0.0.0 -p 8000 core.asgi:application
```

or

```bash
uvicorn core.asgi:application --host 0.0.0.0 --port 8000 --workers 4
```

More than one worker **requires** `REDIS_URL`: the in-memory channel layer cannot
cross processes, and clients on other workers silently stop receiving updates.

## 4. Build and serve the frontend

```bash
cd frontend
VITE_API_BASE_URL=https://api.dayflow.app/api \
VITE_WS_URL=wss://api.dayflow.app/ws/updates/ \
npm ci && npm run build
```

`dist/` is static. Serve it from any CDN or web server; `frontend/nginx.conf` is
a working config with security headers, immutable asset caching, and
`index.html` marked `no-store` so clients cannot pin to a stale bundle.

Vite inlines these at build time — changing the API origin means rebuilding.

## 5. Reverse proxy

WebSockets need the upgrade headers, or realtime updates fail with no visible
error:

```nginx
location /ws/ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
}

location /api/ {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The proxy must **overwrite** `X-Forwarded-Proto`, not append to it. The app
trusts that header when `DJANGO_BEHIND_TLS_PROXY=true`, so a proxy that passes a
client-supplied value lets anyone claim HTTPS.

---

## Docker

```bash
docker compose up --build
```

`docker-compose.yml` runs Postgres, Redis, the API and the built SPA. It is a
**development** stack: it uses a development database password and exposes
Postgres on the host. For production, use the same Dockerfiles with managed
Postgres and Redis, real secrets from your platform's secret store, and no
published database port.

Both images run as a non-root user and carry health checks.

---

## Platform notes

**Render / Railway / Fly.** Set `DJANGO_BEHIND_TLS_PROXY=true` (the default) —
TLS terminates at the platform edge. Use the platform's managed Postgres and
Redis. Put `migrate` in the release command, not the start command.

**Render specifically.** `DJANGO_ALLOWED_HOSTS` accepts `*.onrender.com`; the
settings normalise it to `.onrender.com`.

**Heroku.** `web: daphne -b 0.0.0.0 -p $PORT core.asgi:application`, with
`release: python manage.py migrate --no-input`.

---

## Pre-launch checklist

**Configuration**
- [ ] `DJANGO_DEBUG` is false — confirm with `manage.py check --deploy`
- [ ] `DJANGO_SECRET_KEY` is unique to this environment and not in Git
- [ ] `DJANGO_ALLOWED_HOSTS` lists exactly your API hostnames
- [ ] `DJANGO_CORS_ALLOWED_ORIGINS` lists exactly your frontend origins
- [ ] TLS terminates before the app and HTTP redirects to HTTPS
- [ ] `DJANGO_BEHIND_TLS_PROXY` matches reality

**Data**
- [ ] Postgres, not SQLite (`DJANGO_ALLOW_SQLITE` unset)
- [ ] Automated backups on, with a restore actually tested
- [ ] `DJANGO_DB_SSL_REQUIRE=true` unless the database is on a private network
- [ ] Redis reachable, and required if more than one worker

**Billing** — see [BILLING.md](./BILLING.md)
- [ ] Live keys, live prices, live webhook endpoint and its own signing secret
- [ ] Customer portal activated in live mode
- [ ] One real transaction completed end to end

**Security**
- [ ] `manage.py check --deploy` reports no issues
- [ ] `make audit` passes — the full security regression suite
- [ ] **Razorpay keys rotated.** The keys committed in the old
      `settings.py` are in Git history and must be treated as compromised
      regardless of no longer being used (audit V-34).
- [ ] Production database checked for rogue `ADMIN` rows created through the old
      registration hole: look for multiple `role='ADMIN'` accounts in one
      organization that the customer does not recognise (audit V-01).
- [ ] Email deliverability verified — password reset depends on it

**Operations**
- [ ] Logs shipped somewhere searchable (`dayflow.audit`, `dayflow.billing`,
      `dayflow.security`, `django.request`)
- [ ] Error tracking wired up; `error_id` in a 500 response correlates with the log
- [ ] Uptime check on `GET /api/billing/plans/` — public and dependency-light
- [ ] Alerts on webhook failures and 5xx rate

---

## Upgrading an existing deployment

The tenancy migration is the significant one: `accounts.0011`–`0014` convert
`company_name` strings into `Organization` rows, fold in `CompanyConfig` and
`CompanyLogo`, and move `CustomUser.salary` into `payroll.EmployeeSalary` before
dropping the old columns.

1. **Back up the database.** The salary move and the negative-pay clamp
   (`payroll.0005`) are not fully reversible.
2. Migrate a copy first and check the result:
   ```sql
   SELECT o.name, o.slug, COUNT(u.id)
   FROM organizations_organization o
   LEFT JOIN accounts_customuser u ON u.organization_id = o.id
   GROUP BY o.id ORDER BY o.name;

   -- Should be empty except for platform superusers:
   SELECT login_id, email FROM accounts_customuser WHERE organization_id IS NULL;
   ```
3. Slug-equivalent company names **merge** into one organization — check that
   every merge is genuinely the same customer and not two unrelated ones.
4. Users with a blank `company_name` are left unlinked and will get a 403 until
   assigned. Superusers are expected here; anyone else needs attention.
5. Deploy the frontend and backend together. The API contract changed:
   registration takes different fields, login returns a nested `user` object,
   list endpoints are paginated, and employee payloads no longer include
   `salary` or `company_name`.

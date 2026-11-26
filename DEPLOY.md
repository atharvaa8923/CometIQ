# Deploying CometIQ

CometIQ is one container (API + web app) plus PostgreSQL. Uploaded certificates are stored in the
database, so no persistent disk is needed.

**Faculty pilot:** follow [docs/PILOT-DEPLOY.md](docs/PILOT-DEPLOY.md) (Render Blueprint `render.pilot.yaml`: two values to enter, readiness check and drills), then send [docs/UTD-IT-REQUEST.md](docs/UTD-IT-REQUEST.md) for NetID and Canvas.

## Option 1 — Render (recommended, ~15 minutes)

1. **Push this project to GitHub** (private repo is fine).
2. In Render: **New → Blueprint** → pick the repo. `render.yaml` creates:
   - `cometiq-db` (managed PostgreSQL, daily backups)
   - `cometiq` (Docker web service, HTTPS on `https://cometiq-xxxx.onrender.com`, health check `/api/health`)
3. Fill in the secrets Render asks for:

   | Variable | Value |
   |---|---|
   | `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | Your first admin login (password 12+ chars) |
   | `CORS_ORIGINS` | Your site URL, e.g. `https://cometiq.yourdomain.edu` |
   | `ANTHROPIC_API_KEY` | From console.anthropic.com. Turns on Claude for extraction, insights, CometForge and match explanations |
   | `NEBULA_API_KEY` | From UTD Nebula Labs (Discord). Live sections & grades |
   | `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | developer.adzuna.com (free tier). Business-role postings |
   | `USAJOBS_API_KEY` / `USAJOBS_EMAIL` | developer.usajobs.gov (free). Federal postings |
   | `APP_URL` | Your public URL (used in email links) |
   | `RESEND_API_KEY` / `EMAIL_FROM` | resend.com (free tier). Password reset and notification emails; verify your domain (SPF/DKIM) |
   | `SENTRY_DSN` | sentry.io project (free tier). Error alerts; personal data is scrubbed |

   `JWT_SECRET` is generated automatically. Leave unused keys empty; each feature falls back gracefully.
4. Deploy. On first start CometIQ creates the institution, loads the UTD JSOM catalog (39 programs, 331 courses),
   creates your admin, and runs an initial job sync. Sign in, open **Organization**, and:
   - copy the **join code** and share it with faculty, advisors, students and employers;
   - click **Test connection** under Claude AI;
   - check **Live job market sources** (nightly sync after `JOB_SYNC_HOUR_UTC`, default 07:00 UTC).
5. **Custom domain:** Render → service → Settings → Custom Domains → add `cometiq.yourdomain.edu`, create the
   CNAME it shows at your DNS provider; HTTPS certificates are issued automatically. Update `CORS_ORIGINS`.

Plan notes: the web service needs an always-on plan (Starter or above) for the nightly sync. Free instances sleep.
Scale to 2+ instances any time; the nightly sync uses a database lock so it runs once.

## Option 2 — Railway / Azure / any Docker host

```bash
docker build -t cometiq .
docker run -p 8000:8000 \
  -e ENV=production -e SEED_DEMO=false \
  -e DATABASE_URL=postgresql://user:pass@host:5432/cometiq \
  -e JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))") \
  -e BOOTSTRAP_ADMIN_EMAIL=you@utdallas.edu -e BOOTSTRAP_ADMIN_PASSWORD='a-long-password' \
  -e ANTHROPIC_API_KEY=... cometiq
```
- **Railway:** New Project → Deploy from GitHub (uses the Dockerfile) → add the PostgreSQL plugin → set the variables above
  (`DATABASE_URL` is provided; `postgres://` URLs are normalized automatically) → Settings → Networking → Generate Domain / custom domain.
- **Azure:** Azure Container Apps (from the image) + Azure Database for PostgreSQL Flexible Server; set the same variables;
  enable HTTPS ingress and a custom domain on the Container App.
- Put the app behind HTTPS (all three platforms do this for you). `ENV=production` turns on HSTS and refuses a weak `JWT_SECRET`.

## Demo vs. production
- `SEED_DEMO=true` creates demo users whose password is public (`CometIQ2026!`) plus fictional sample jobs. Use it only
  for a throwaway demo site.
- `SEED_DEMO=false` (the Render default) creates no demo users; the login page hides the demo buttons.

## Before real users
Work through [LAUNCH-CHECKLIST.md](LAUNCH-CHECKLIST.md): UTD security/FERPA/legal reviews, email domain, monitoring,
backup restore test and pilot setup.

## Operations
- **Backups:** managed PostgreSQL backups (Render: daily; enable point-in-time recovery on paid plans).
- **Health:** `/api/health` (liveness, used by Render) and `/api/health/ready` (database, job queue, last sync; 503 when
  degraded): point an uptime monitor at it. Admins see the same under Organization → System health.
- **Logs:** JSON logs (`LOG_FORMAT=json`) with a request ID on every line; users see the same ID ("reference …") on errors.
  Unhandled errors and browser errors go to Sentry when `SENTRY_DSN` is set.
- **Background jobs:** AI analysis, syllabus generation, catalog/syllabus imports and emails run in a database-backed queue
  (`TASK_WORKERS` threads per instance; jobs survive restarts and are claimed once across instances).
- **University integrations:** single sign-on, Canvas, Canvas Credentials, Open Badges signing and Handshake are set up
  with environment variables; follow [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md). In production set `SECRETS_KEY`
  (encrypts Canvas tokens; the Render blueprint generates one) and `OB_SIGNING_KEY` (signs Open Badges).
- **Scaling:** set `WEB_CONCURRENCY` (uvicorn worker processes, about one per CPU core; the image defaults to 2). Each
  process opens up to `DB_POOL_SIZE + DB_MAX_OVERFLOW` (8 + 12) database connections: keep the total below PostgreSQL's
  `max_connections`. Caches and rate-limit counters are per process; cached views are invalidated across all of them.
  Measured capacity: [docs/performance/LOAD-TEST.md](docs/performance/LOAD-TEST.md).
- **Rate limits:** expensive endpoints (AI, simulator, rankings, exports) have per-user budgets per minute and return 429
  with `Retry-After`; tune with `RATE_LIMIT_MULTIPLIER` or turn off with `RATE_LIMITS_ENABLED=false`.
- **Retention:** a daily job removes finished tasks, read notifications, expired password resets, idempotency keys and
  other operational data (`RETENTION_*` settings; `python -m app.manage retention --dry-run` shows what it would delete).
- **Upgrades:** push to GitHub → auto-deploy. Database migrations (Alembic) run automatically at start, one instance at a
  time (PostgreSQL advisory lock).
- **Security:** bcrypt passwords, JWT (24 h), role-based access on every endpoint, per-organization data isolation,
  login rate limiting, security headers, uploads checked by file signature (PDF/PNG/JPG/WebP, 10 MB max).

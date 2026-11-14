# Deploying CometIQ

CometIQ is one container (API + web app) plus PostgreSQL. Uploaded certificates are stored in the
database, so no persistent disk is needed.

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

## Operations
- **Backups:** managed PostgreSQL backups (Render: daily; enable point-in-time recovery on paid plans).
- **Logs:** the platform's log viewer; sync runs and Claude errors are logged under `cometiq.sync` / `cometiq.ai`.
- **Upgrades:** push to GitHub → auto-deploy. New tables are created automatically at start; for column changes on an
  existing database, add Alembic migrations before upgrading a production instance.
- **Security:** bcrypt passwords, JWT (24 h), role-based access on every endpoint, per-organization data isolation,
  login rate limiting, security headers, uploads checked by file signature (PDF/PNG/JPG/WebP, 10 MB max).

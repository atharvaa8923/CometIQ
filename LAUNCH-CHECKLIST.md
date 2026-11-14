# CometIQ — UTD pilot launch checklist

Everything in **Software** is built and tested. The **Institution** items need people at UTD and
can't be done in code. Start them early; reviews take weeks.

## 1. Institution (owners: you + UTD offices)
- [ ] **Executive sponsor** (e.g. JSOM associate dean) and a named **system owner** for CometIQ.
- [ ] **UTD Information Security review** of the hosting setup (Render/Azure, PostgreSQL, Claude API, Nebula API).
      Bring `DEPLOY.md`, this checklist and the security summary below.
- [ ] **FERPA / Registrar sign-off.** CometIQ stores education records (courses, plans, advisor notes).
      Confirm: which data may be stored, that employer visibility is opt-in, data retention, and who handles
      deletion requests (admins can erase a user under Users → Delete).
- [ ] **Legal review of the Privacy Notice and Terms** (`/privacy`, `/terms`). They are written for this system
      but are drafts until UTD counsel approves them. When text changes, bump `POLICY_VERSION`
      in `backend/app/routers/privacy.py` and every user is asked to accept the new version.
- [ ] **AI data processing approval.** With `ANTHROPIC_API_KEY` set, syllabi, resumes and course text are sent to
      Anthropic's API (not used for model training under commercial terms). Get approval, or leave the key unset to keep
      everything on the built-in engine.
- [ ] **Nebula Labs API key** (UTD Nebula Labs Discord) and permission to use their data in the pilot.
- [ ] **Accessibility contact** for the `/accessibility` page (Texas requires WCAG 2.1 AA; automated axe audits pass).
- [ ] Optional later: **UTD single sign-on** (Microsoft Entra / SAML) through UTD IT.

## 2. Hosting (owner: you, ~1 hour with DEPLOY.md)
- [ ] Code in a private GitHub repo; Render Blueprint deployed (`render.yaml`): web service + managed PostgreSQL.
- [ ] Custom domain with HTTPS; set `APP_URL` and `CORS_ORIGINS` to it.
- [ ] `ENV=production`, `SEED_DEMO=false`, strong `JWT_SECRET` (auto-generated), bootstrap admin set.
- [ ] **Email:** create a Resend account, verify your sending domain (SPF + DKIM DNS records), set `EMAIL_PROVIDER=resend`,
      `RESEND_API_KEY`, `EMAIL_FROM` (e.g. `CometIQ <no-reply@cometiq.yourdomain.edu>`). Test with "Forgot password".
- [ ] **Keys:** `ANTHROPIC_API_KEY` (+ `AI_DAILY_LIMIT_PER_ORG`), `NEBULA_API_KEY`, `ADZUNA_*` and/or `USAJOBS_*`.
- [ ] **Monitoring:** create a Sentry project → `SENTRY_DSN`; add an uptime monitor on `https://<domain>/api/health/ready`
      (alerts by email/SMS when it stops returning 200).
- [ ] **Backups:** confirm daily PostgreSQL backups are on; do one **test restore** into a scratch database.

## 3. First-day setup in the app (owner: admin)
- [ ] Sign in as the bootstrap admin → Organization:
  - [ ] System health shows **Healthy**; Claude **Test connection** succeeds.
  - [ ] **Import full UTD catalog** (Nebula) — graduate courses for the pilot.
  - [ ] **Sync now** for job sources; check postings appear for business roles.
- [ ] CometGap → Program heatmap → **Analyze official syllabi** for the pilot program.
- [ ] Share the **join code** with pilot faculty, advisors, students and employers.

## 4. Pilot (one semester)
- Scope: **MS Business Analytics & AI** — 2–3 faculty, 1–2 advisors, ~30 students, 3 partner employers.
- Success measures (visible on the dashboard): syllabi analyzed and average coverage; Forge drafts approved and projected
  lift; % of students with a career goal and an approved plan; verified certifications; applications, interviews, offers.
- Collect feedback at weeks 4 and 12; review Sentry errors weekly.

## Security summary (for reviewers)
- HTTPS only (HSTS in production); bcrypt passwords; JWT sessions (24 h) revoked on password change/reset;
  login and reset rate limits; single-use, 30-minute, hashed reset tokens; no account enumeration.
- Role-based access on every API endpoint (admin, faculty, advisor, student, employer) and per-institution data isolation;
  employers see only students who opted in, and never full resume text, grades or plans.
- Uploads checked by file signature (PDF/PNG/JPG/WebP), 10 MB limit, stored in the database; syllabus downloads restricted to
  HTTPS `utdallas.edu` hosts (SSRF protection).
- Audit log of sensitive actions; privacy controls: consent tracking, data export, account deletion, admin erasure.
- Error reports to Sentry exclude request bodies, cookies, auth headers and user identity.
- 62 automated tests (SQLite and PostgreSQL); axe WCAG 2.1 AA audit: 0 violations on all pages and main dialogs.

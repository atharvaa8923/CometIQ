# CometIQ — AI Intelligence for Education, Skills & Talent

**From industry demand to student success.** CometIQ is a multi-tenant SaaS platform that connects
industry needs, university curriculum, student goals and employer opportunities through four modules
that share one knowledge graph:

| Module | Who | What it does |
|---|---|---|
| **CometGap** — Curriculum–Industry Gap Analysis | Faculty, admins | Upload a syllabus (PDF/DOCX/TXT) and get a coverage score against live job postings. Shows priority gaps, emerging technologies, courses that already teach each gap, a program-wide course × skill heatmap, and PDF/Excel reports. |
| **CometForge** — AI Course & Syllabus Generation | Faculty, admins | Turns a gap report into an updated syllabus: weekly modules, Bloom-aligned learning outcomes, rebalanced assessments, an industry project, AACSB/ABET and program-goal mapping, and a projected before/after score. Supports editing, versions, approval and Word/PDF export. |
| **CometPath** — AI Degree & Career Planner | Students, advisors | Program/concentration progress with core OR-groups. Builds a prerequisite-safe semester-by-semester plan optimized for a career goal, tracks career readiness, recommends what to take next, and suggests a concentration when another fits the goal better. Also: **what-if plans** ("what if I switch to Finance?"), **advisor review and approval**, **PDF plan export**, and **live UTD sections and grade distributions** from Nebula Labs. |
| **CometMatch** — Student–Employer Talent Matching | Students, employers, advisors | Students upload a resume and see their best-fit jobs. Employers post roles, see ranked candidates and **search all opted-in students** by skill. Every fit score has a transparent breakdown with evidence, an **AI explanation**, and **resume tips**. Students document **courses, certifications and projects with proof**; once an admin or advisor verifies them they count as full evidence, and **verified certifications add bonus points** (default +10). **Skills to learn next** links straight into CometPath. |

The **feedback loop**: job postings → CometGap finds gaps → CometForge closes them → approved syllabi update
the course's skills in the knowledge graph → CometPath recommends those courses → CometMatch shows employers
the resulting skills. The dashboard tracks the four outcomes: more relevant curricula, personalized
student journeys, stronger employer partnerships and better career outcomes.

---

## Quick start

### Option A: one command (Python 3.11+ and Node 20+)
```bash
./run.sh
```
Open http://localhost:8000. It uses SQLite and seeds the demo data on first start.

### Option B: Docker (app + PostgreSQL)
```bash
cp .env.example .env    # set JWT_SECRET; optionally ANTHROPIC_API_KEY
docker compose up --build
```

### Demo accounts (password `CometIQ2026!`)
| Role | Email |
|---|---|
| Faculty | faculty@cometiq.app |
| Student | student@cometiq.app |
| Employer | employer@cometiq.app |
| Advisor | advisor@cometiq.app |
| Admin | admin@cometiq.app |

The login page also has one-click demo buttons. To join the demo institution as a new user, use join code **COMET-UTD**.
Registering with a *new institution name* creates a separate tenant (organization) and makes you its admin.

### Development (hot reload)
```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cd backend && ../.venv/bin/uvicorn app.main:app --reload      # API on :8000, docs at /docs
cd frontend && npm install && npm run dev                      # UI on :5173 (proxies /api)
```

### Tests
```bash
cd backend && ../.venv/bin/python -m pytest -q
# against PostgreSQL:
TEST_DATABASE_URL=postgresql+psycopg://user:pass@host/db ../.venv/bin/python -m pytest -q
```

---

**Deploying for real:** see [DEPLOY.md](DEPLOY.md) (Render blueprint included). Production mode (`SEED_DEMO=false`) creates no demo accounts.

## Configuration (`.env`)

| Variable | Purpose |
|---|---|
| `JWT_SECRET` | **Required in production** (32+ chars; the app refuses to start with `ENV=production` and a weak secret). |
| `DATABASE_URL` | Defaults to SQLite. Production: `postgresql+psycopg://…` |
| `ANTHROPIC_API_KEY` | Optional. Turns on Claude for skill extraction, gap insights and syllabus generation (`AI_MODEL`, default `claude-opus-5-5`). |
| `NEBULA_API_KEY` | Optional. Live UTD sections, professors and grade distributions in course details (cached 6 h). |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`, `USAJOBS_API_KEY` / `USAJOBS_EMAIL` | Optional live job feeds. Synced nightly (`JOB_SYNC_HOUR_UTC`) and on demand from Organization → Live job market sources. |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` | Production: the first admin account. |
| `SEED_DEMO` | Seed the demo institution on first start. |

### AI engines
Every AI feature has two engines that return the **same structured output**:
- **Built-in engine** (always available, deterministic): a 136-skill taxonomy with aliases, rule-based
  extraction, a teaching-content library and transparent scoring formulas.
- **Claude** (when `ANTHROPIC_API_KEY` is set): structured outputs validated against Pydantic schemas, with server-side
  refusal fallback enabled. Claude can only choose skills from the taxonomy, so results stay comparable. If a Claude
  call fails, the request falls back to the built-in engine instead of failing.

### Job market data
- ~50 seed postings across 14 role families (fictional DFW companies), so the platform works offline on day one.
- **Sync live postings**: free GitHub new-grad/internship lists (US roles; titles are mapped to role-family skill profiles), which are mostly software roles.
- **Adzuna** and **USAJobs** APIs (with keys) for business roles, **CSV import** (`title, company, location, description, url`), manual entry, and employer posts in CometMatch.
- **Nightly automatic sync**, a one-time initial sync on a fresh deployment, and synced postings expire after 60 days.

---

## How the scores work (transparent by design)

- **CometGap coverage** = Σ demand × status weight / Σ demand over the top-N market skills.
  Demand is the share of target postings asking for the skill (required = 1.0, preferred = 0.5). Status:
  covered (≥2 mentions or named in the schedule) = 1, partial (one mention) = 0.5, missing = 0.
  Priority: critical ≥40% of postings, high ≥25%, medium ≥12%.
- **CometForge projection** re-scores the same analysis with the draft's added skills counted as covered.
- **CometPath** prerequisites: edges in the same group are OR, different groups are AND. Core OR-groups are
  satisfied by any one option. Course career-fit = Σ (skill demand for the goal × course-skill weight).
- **CometMatch fit** = base + bonus. Base = Σ w × evidence level / Σ w, with w = 1 for required and 0.5 for preferred. Evidence:
  resume, completed course or verified course/certification/project = 1.0 (a secondary course topic = 0.6); in-progress course or
  pending (unverified) evidence = 0.5. Bonus = points of verified certifications/projects whose skills the job needs (max +15).
  Nothing else affects the score.

---

## Architecture

```
cometiq/
├── backend/                 FastAPI + SQLAlchemy (SQLite or PostgreSQL)
│   ├── app/main.py          one app: REST API under /api + serves the built React app
│   ├── app/models.py        shared knowledge graph (orgs, users, skills, courses, prereqs,
│   │                        programs, jobs, syllabi, analyses, drafts, plans, applications, audit)
│   ├── app/routers/         auth · admin · catalog · dashboard · jobs · gap · forge · path · match
│   ├── app/services/        skills (extraction) · gap · forge · path · match · jobs · sources · reports · ai
│   ├── app/data/            catalog.json (JSOM programs/courses/prereqs), taxonomy, seed jobs, forge library
│   └── tests/               end-to-end API tests
├── frontend/                React 19 + TypeScript + Tailwind (Vite)
├── Dockerfile               multi-stage: builds UI, runs API serving it
└── docker-compose.yml       app + PostgreSQL
```

Security: bcrypt password hashing, JWT auth, role-based access (admin / faculty / student / employer) on every
endpoint, per-organization data isolation, upload type/size limits, an audit log of key actions, and employers
see skill evidence rather than full resume text.

### Where the data came from
- **JSOM Degree Planner** (Node/Express): 39 graduate programs, 331 courses with catalog descriptions,
  188 prerequisite edges with OR groups, core requirements and 72 concentrations. All of it was migrated into `catalog.json`.
- **SyllabusCheck** (FastAPI/Celery): the gap-analysis approach, UTD department skill categories and job-source
  ideas were reimplemented without Celery, Redis or torch, so the stack is a single process.

> ⚠️ The original JSOM planner zip contains a `.env` with what looks like a live Nebula API key. It was **not**
> copied here. Consider rotating it.

### What has and hasn't been tested live
- Tested end to end in a browser and by 32 API tests (SQLite and PostgreSQL): all four modules, roles, evidence verification,
  advisor reviews, what-if, PDFs, talent search, production seeding.
- **Claude, Nebula, Adzuna and USAJobs** are implemented against their documented APIs and tested with fakes/fixtures, but have
  **not yet been called live** (no keys and/or the hosts were unreachable from the build environment). After deploying, use
  Organization → *Test connection* and *Sync now* to confirm each one.

### Roadmap ideas
SSO (Google/SAML), email notifications, Alembic migrations, an interactive knowledge-graph map, and an AI chat assistant.

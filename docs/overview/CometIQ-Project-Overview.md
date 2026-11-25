# CometIQ: Project Overview

**From industry demand to student success.** CometIQ is a web platform (SaaS) for universities. It connects four groups that
usually work separately: **employers** (what skills jobs ask for), **faculty** (what courses teach), **students** (what they
learn and plan) and **advisors and administrators** (who verify and approve). All four share one knowledge graph of
*jobs → skills → courses → students*.

This document explains what has been built so far, how each part works, what it looks like, and which tools were used for the
frontend and backend. All screenshots come from the running application with its demo data.

---

## Contents
1. [At a glance](#1-at-a-glance)
2. [The idea: one feedback loop](#2-the-idea-one-feedback-loop)
3. [Who uses it](#3-who-uses-it)
4. [Walkthrough with screenshots](#4-walkthrough-with-screenshots)
   - [4.1 Landing, sign-in and dashboards](#41-landing-sign-in-and-dashboards)
   - [4.2 CometGap: curriculum vs. industry gap analysis](#42-cometgap-curriculum-vs-industry-gap-analysis)
   - [4.3 Faculty review and the faculty pilot](#43-faculty-review-and-the-faculty-pilot)
   - [4.4 Course history: decisions, versions and comparisons](#44-course-history-decisions-versions-and-comparisons)
   - [4.5 Curriculum: proposals, AACSB map and outcomes](#45-curriculum-proposals-aacsb-map-and-outcomes)
   - [4.6 CometForge: AI syllabus generation](#46-cometforge-ai-syllabus-generation)
   - [4.7 CometPath: degree and career planner](#47-cometpath-degree-and-career-planner)
   - [4.8 CometMatch: students and employers](#48-cometmatch-students-and-employers)
   - [4.9 Advising, verification and the knowledge graph](#49-advising-verification-and-the-knowledge-graph)
   - [4.10 Scorecard, copilot, simulator, skill stacks, partner projects and Ask CometIQ](#410-scorecard-copilot-simulator-skill-stacks-partner-projects-and-ask-cometiq)
5. [How the scores work](#5-how-the-scores-work)
6. [Architecture](#6-architecture)
7. [Tools and technologies](#7-tools-and-technologies)
8. [Data model](#8-data-model)
9. [Security, privacy, accessibility and monitoring](#9-security-privacy-accessibility-and-monitoring)
10. [Testing and quality](#10-testing-and-quality)
11. [Project structure](#11-project-structure)
12. [How it was built: timeline](#12-how-it-was-built-timeline)
13. [Running and deploying](#13-running-and-deploying)
14. [What is real, and what still needs UTD](#14-what-is-real-and-what-still-needs-utd)
15. [Glossary](#15-glossary)

---

## 1. At a glance

| | |
|---|---|
| **Modules** | CometGap, CometForge, CometPath, CometMatch, Curriculum (scorecard, proposals, curriculum map, simulator, skill stacks, outcomes) and Ask CometIQ |
| **Roles** | Administrator, faculty, student, employer, academic advisor |
| **Catalog data** | 39 JSOM graduate programs, 331 courses, 188 prerequisite links (the full UTD catalog can be imported from Nebula Labs) |
| **Skill taxonomy** | 136 skills in 12 categories, with aliases (e.g. "pandas" counts as Python) |
| **Backend** | Python 3.13, FastAPI, SQLAlchemy, Alembic, LangGraph; about 10,900 lines; 173 API endpoints; 42 database tables; 5 migrations |
| **Frontend** | React 19, TypeScript, Tailwind CSS, Vite; about 6,100 lines |
| **Tests** | 75 automated API tests (about 1,500 lines), passing on both SQLite and PostgreSQL |
| **Accessibility** | WCAG 2.1 AA checked with axe-core: no violations on any page |
| **AI** | Claude (optional), plus a built-in engine that gives the same structured output without any API key |

---

## 2. The idea: one feedback loop

The poster's idea is a loop in which each module feeds the next:

```mermaid
flowchart LR
    J[Job postings<br/>Adzuna · USAJobs · GitHub lists · CSV · employers] --> G[CometGap<br/>finds curriculum gaps]
    G --> R[Faculty review<br/>and decisions]
    R --> F[CometForge<br/>drafts the syllabus change]
    F --> P[Curriculum proposal<br/>committee approves]
    P --> V[New syllabus version<br/>knowledge graph updated]
    V --> CP[CometPath<br/>recommends the course]
    V --> B[Faculty-verified<br/>skill badges]
    CP --> M[CometMatch<br/>students ↔ employers]
    B --> M
    M --> O[Outcomes<br/>did the change help?]
    O --> G
```

1. **Job postings** show which skills employers ask for.
2. **CometGap** compares a syllabus with those postings. The keyword score only ranks what to look at first.
3. **Faculty** review each gap ("Do students actually practice this?") and decide what to do about it.
4. **CometForge** drafts the change, and the **curriculum committee** reviews it like a pull request.
5. The approved text becomes the next **syllabus version**, and the knowledge graph learns that the course now teaches the skill.
6. **CometPath** recommends the course to students with matching career goals, and students who complete it earn **faculty-verified badges**.
7. **CometMatch** shows employers those verified skills. **Outcomes** then compare student groups before and after the change.

---

## 3. Who uses it

| Role | Main screens | What they do |
|---|---|---|
| **Faculty** | CometGap, CometForge, Course history, Curriculum | Analyze syllabi, review gaps, record decisions, draft and propose changes, review colleagues' proposals, set curriculum-map levels |
| **Student** | CometPath, CometMatch | Plan the degree, run what-if scenarios, submit courses and certificates with proof, earn badges, find jobs |
| **Employer** | CometMatch | Post jobs, see ranked candidates, search all opted-in students, count only faculty-verified skills |
| **Advisor** | Advising, Verifications | Review and approve student plans, verify course completions and certificates |
| **Administrator** | Everything, plus Organization and Users | Manage people and data sources, sync jobs, import the catalog, confirm catalog years, delete accounts on request |

Each institution is a separate **organization** (tenant). People join with the institution's join code, and an organization's
data is never visible to another organization.

---

## 4. Walkthrough with screenshots

### 4.1 Landing, sign-in and dashboards

![Landing page](images/01-landing.jpg)
*The public landing page explains the four modules and the feedback loop.*

![Sign in](images/02-login.jpg)
*Sign-in. The demo has one-click demo accounts. A faculty-only pilot shows a notice instead and allows only faculty and admin accounts.*

![Admin dashboard](images/03-admin-dashboard.jpg)
*Administrator dashboard: the four outcomes from the poster (more relevant curricula, personalized student journeys, stronger
employer partnerships, better career outcomes) and the most common gaps across analyzed courses.*

![Faculty dashboard](images/05-faculty-dashboard.jpg)
*Every role sees its own dashboard with a suggested next step.*

### 4.2 CometGap: curriculum vs. industry gap analysis

Faculty upload a syllabus (PDF, Word or text), import the official UTD syllabus through Nebula Labs, or paste text. CometIQ
extracts the skills the syllabus mentions and compares them with job postings.

![CometGap home](images/10-gap-home.jpg)
*My syllabi, with each course's latest coverage score and links to its report and history.*

![Upload](images/11-gap-upload.jpg)
*Analyze a syllabus. Optionally choose a **documented job sample**, a frozen set of postings with a written sampling method.*

![Gap report](images/15-gap-report.jpg)
*The gap report: the mention-based coverage score, a separate faculty-reviewed score, the evidence behind the report (job sample,
number of postings, sources, posting dates, sampling method), recorded inputs, and actionable insights.*

![Market demand](images/12-market.jpg)
*Market demand: the top skills across current postings, with emerging technologies marked.*

![Program heatmap](images/13-heatmap.jpg)
*Program heatmap: courses × in-demand skills for a whole program, showing where each skill is taught.*

![Job postings](images/14-jobs.jpg)
*Job postings with their extracted skills. Sources: seed data, GitHub new-grad lists, Adzuna, USAJobs, CSV import and employer posts.*

Reports export to **PDF** and **Excel**, and the findings export to **CSV**.

### 4.3 Faculty review and the faculty pilot

The keyword score is only a signal. Faculty decide whether students actually **practice or demonstrate** each skill.

![Evidence card](images/p1-report-top.jpg)
*The evidence behind a report: the job sample and when it was frozen, posting count, sources, date range and sampling method.*

![Review a skill](images/p2-review-row.jpg)
*For each skill: the syllabus excerpt, how many sampled postings ask for it (required and preferred), where those postings came
from and when, other courses that teach it, and the faculty classification.*

![Saved correction](images/p3-review-saved.jpg)
*A correction ("system said missing, faculty say practiced") needs a written rationale, and it is saved with the reviewer's name and the date.*

![Approved for the pilot](images/p4-approved.jpg)
*A syllabus is used in the pilot only after its instructor of record approves it.*

![Pilot review](images/p5-pilot.jpg)
*Pilot review tracks which findings faculty confirmed, corrected or acted on, and lists every correction with its rationale.*

![Job samples](images/p6-samples.jpg)
*Documented job samples: frozen sets of postings with their method, sources and date range, downloadable as CSV.*

![Catalog year](images/p7-catalog-year.jpg)
*The program's catalog year, confirmed by the program owner and recorded with who confirmed it and when.*

The pilot setup also includes a separate pilot environment (`render.pilot.yaml`), a faculty-only mode (`PILOT_ROLES=admin,faculty`),
a command that removes demo data, and backup/restore and deletion drills. See `PILOT-PLAN.md`, `PILOT-RUNBOOK.md` and `PILOT-AGREEMENT.md`.

### 4.4 Course history: decisions, versions and comparisons

**Decision records.** For each reviewed gap, faculty choose *Add to this course*, *Covered elsewhere* (naming the course),
*Defer* (naming a term to revisit) or *Out of scope*. Each decision saves the rationale, the reviewer, the date and the exact
evidence versions it was based on.

![Decision editor](images/d1-decision-editor.jpg)
*Recording a course decision on a reviewed gap.*

![Decision log](images/d5-decisions.jpg)
*The course's decision log: each decision with its evidence versions (syllabus version and fingerprint, job sample, catalog year,
scoring version) and status. Older decisions stay in the history.*

![Proposed change beside current syllabus](images/d6-proposed.jpg)
*Accepted additions generate a CometForge draft, shown beside the current syllabus for each skill and for the whole document.*

**Versions and comparisons.** Every report records exactly what it was based on: the syllabus version, a frozen snapshot of the job
postings, the catalog version and the scoring version. This lets CometIQ explain *why* a score changed.

![Course history](images/d3-history.jpg)
*Coverage over time, and each change split into **course revision** (the syllabus changed), **demand change** (the job sample
changed) and **method update** (the scoring formula or skill list changed). The three parts always add up to the total change.*

![Comparison detail](images/d4-compare.jpg)
*One comparison in detail: which skills changed and why, the syllabus lines added or removed, and any job-sample, catalog or method changes.*

![Reproducibility](images/d2-inputs.jpg)
*Every report can be recomputed from its recorded inputs. "Verify reproducibility" shows that the result is identical.*

### 4.5 Curriculum: proposals, AACSB map and outcomes

**Curriculum proposals** work like pull requests in software teams:

![Proposal diff](images/c1-proposal-diff.jpg)
*A side-by-side diff against the current syllabus, a comment attached to a specific line, and a colleague's "request changes".*

![Approved proposal](images/c2-proposal-approved.jpg)
*After the author revises and resubmits, colleagues approve. Only votes on the current revision count, and authors can't approve
their own proposal. An approved proposal can be **adopted** as the next syllabus version.*

![Change request form](images/c3-change-form.jpg)
*Each proposal generates a course change request (PDF or Word): justification, current vs. proposed outcomes, impact on other
courses, evidence and approvals.*

![Curriculum map](images/c4-map.jpg)
*The AACSB-style curriculum map: where each in-demand skill is **I**ntroduced, **P**racticed or **M**astered across a program.
Unverified signals are marked with \*. Flags show skills that are never practiced, never mastered, or taught in several courses.
It exports to Excel for accreditation.*

![Outcomes](images/c7-outcomes.jpg)
*Outcomes compare students who completed a course before and after a change, in groups of at least 10 students only. It is an
observational comparison, not proof of cause.*

### 4.6 CometForge: AI syllabus generation

![Forge home](images/20-forge-home.jpg)
*Draft syllabi with their current and projected coverage.*

![Forge editor](images/21-forge-editor.jpg)
*The draft editor: weekly modules, Bloom-aligned learning outcomes, rebalanced assessments, an industry project, AACSB/ABET
mapping, version history, approval, and Word/PDF export.*

### 4.7 CometPath: degree and career planner

![Student dashboard](images/40-student-dashboard.jpg)
*The student dashboard.*

![Semester plan](images/41-path-plan.jpg)
*A prerequisite-safe, semester-by-semester plan optimized for the student's career goal, with career readiness before and after.*

![Degree progress](images/42-path-progress.jpg)
*Degree progress: core requirements (including "take one of these" OR-groups) and the courses taken.*

![Recommended next](images/43-path-recs.jpg)
*Recommended next courses, and the courses each one unlocks.*

![What-if](images/44-path-whatif.jpg)
*What-if: "What if I switch to Finance?" shows remaining credit hours, graduation term and career readiness side by side, and changes nothing until the student switches.*

Plans can be exported to PDF and submitted to an advisor for approval. With a Nebula API key, course details also show live UTD
sections and grade distributions.

### 4.8 CometMatch: students and employers

![Best-fit jobs](images/50-match-jobs.jpg)
*Best-fit jobs with a transparent fit score. Every point is explained in the breakdown.*

![Evidence portal](images/51-evidence-portal.jpg)
*Students describe courses, certifications and projects and upload proof. Once an advisor verifies an item it counts fully, and
verified certifications add bonus points (usually +10).*

![Skill badges](images/c5-student-badges.jpg)
*Faculty-verified skill badges: earned when faculty confirmed the course teaches the skill **and** an advisor verified the student
completed it. Students can share a verification link.*

![Public badge](images/c6-public-badge.jpg)
*The public verification page that an employer sees from a shared link.*

![Learn next](images/52-learn-next.jpg)
*Skills to learn next, linked back to CometPath courses.*

![Employer candidates](images/55-employer-candidates.jpg)
*Employers see ranked candidates for each job, with AI explanations.*

![Talent search](images/56-talent-search.jpg)
*Talent search across all students who opted in.*

![Faculty-verified search](images/c8-talent.jpg)
*"Count only faculty-verified skills" makes the search count only skills backed by badges.*

### 4.9 Advising, verification and the knowledge graph

![Advising](images/60-advising.jpg)
*Advisors review and approve submitted degree plans.*

![Verifications](images/61-verifications.jpg)
*The verification queue for courses, certifications and projects, with bonus points.*

![Knowledge graph](images/30-knowledge-graph.jpg)
*The interactive knowledge graph: click a job family to see its skills, then the courses that teach them, then the students who have them.*

![Organization](images/04-organization.jpg)
*Organization settings: the join code, people counts, system health, and live job-market sources (sync now, test connection).*

### 4.10 Scorecard, copilot, simulator, skill stacks, partner projects and Ask CometIQ

**Dean's program scorecard.** One page across every program: coverage of analyzed courses and its trend, priority gaps nobody has
decided on, proposals waiting, in-demand skills never practiced or never mastered, badge holders, and a "needs attention" list.

![Program scorecard](images/n1-scorecard.jpg)
*Program scorecard with one program expanded: undecided gaps (linked to their reports), waiting proposals, analyzed courses, and skills never practiced or mastered.*

**Syllabus copilot.** Edit a syllabus and the score, the skill changes, the posting evidence, the curriculum-map position and
possible overlaps update as you type (about 0.2 s per update, using the built-in extractor and the course's recorded job sample).
Save the result as a new semester version or open it directly as a curriculum proposal.

![Syllabus copilot](images/n2-copilot.jpg)
*"You added 'Week 15: SQL joins lab…': SQL moves from missing to covered, +10.7 points", with the 6 of 6 postings behind it.*

**Program simulator.** Try a redesign on a copy of the program: set a skill's level, move a skill between courses, add or remove
a course, add or remove a prerequisite. See program coverage, the I→P→M flags, the longest prerequisite chain and students'
saved plans that would gain a problem (counts only). A circular prerequisite is rejected. Nothing is saved.

![Program simulator](images/n3-simulator.jpg)
*Two changes raise program coverage from 51% to 67.5% and leave two fewer in-demand skills unpracticed.*

**Skill stacks.** Role-ready credentials made of faculty-verified badges (for example *Data Analyst = SQL + Excel + Tableau + Statistics*).
Students see their progress and the next course for each missing skill in CometMatch and CometPath. Employers follow a stack and
are notified when a student who is open to opportunities completes it. Faculty define and edit stacks.

![Student skill stacks](images/n6-student-stacks.jpg)
*A student's progress: Data Analyst 2 of 4, with each verified skill and where it was verified.*

![Stack editor](images/n4-stacks-admin.jpg)
*Faculty manage the stacks.*

![Employer stack alerts](images/n9-employer-stacks.jpg)
*Employers follow stacks and see who completed them.*

**Employer-sponsored projects.** Faculty can share an accepted addition with employer partners. Partners see the course, the skill
and a note written for them, never the internal rationale. They offer a project, dataset or guest session; faculty accept it,
which creates a new CometForge draft whose team project is the sponsor's project. The instructor then records which students
completed it. Each earns a badge naming the partner, and the sponsor gets first look at participants who are open to opportunities.

![Faculty partners tab](images/n5-faculty-partners.jpg)
*Course history → Partners: share accepted additions, accept or decline offers, record completion.*

![Employer partner projects](images/n8-employer-projects.jpg)
*The employer's view: shared needs, their offers and status, and first look at participants.*

![Partner badge](images/n7-partner-badge.jpg)
*The badge a participant earns.*

**Ask CometIQ (LangGraph).** A chat that answers only from CometIQ's stored records, with numbered citations that link to the
source pages. Built as a LangGraph state graph: understand → gather (read-only, permission-scoped queries) → write → verify. Claude
classifies and writes when an API key is configured; otherwise rules and templates do. The verify step removes citations to records
that do not exist, and the agent refuses to answer when it finds no records. "How this was answered" shows each step.

![Ask CometIQ](images/n10-ask.jpg)
*"Which priority gaps have no decision yet?" and "Draft the AACSB summary for Excel", each claim linked to its source.*

---

## 5. How the scores work

Every score is transparent: the formula is shown in the app and in this document.

| Score | Formula |
|---|---|
| **CometGap coverage** (mention-based) | Σ demand × status weight ÷ Σ demand, over the top 30 skills in the job sample. Demand = share of postings asking for the skill (required = 1.0, preferred = 0.5). Status: covered (≥ 2 mentions or named in the schedule) = 1, partial (1 mention) = 0.5, missing = 0. |
| **Faculty-reviewed coverage** | The same formula, but faculty classifications replace the keyword signal where they exist: practiced = 1, mentioned only = 0.5, not covered = 0. Skills marked "not relevant" are left out. |
| **Priority** | critical ≥ 40% of postings · high ≥ 25% · medium ≥ 12% · low otherwise |
| **Change attribution** | Scores all four combinations of {old, new syllabus} × {old, new job sample} with the current method. *Course revision* and *demand change* are each the average effect of swapping that one input. *Method update* is whatever the scoring change accounts for. The parts add up exactly to the total. |
| **CometForge projection** | The same report re-scored with the draft's new skills counted as covered. |
| **CometPath** | Prerequisites: links in the same group are OR, different groups are AND. Course career fit = Σ (skill demand for the goal × course-skill weight). |
| **CometMatch fit** | Base = Σ w × evidence level ÷ Σ w (w = 1 required, 0.5 preferred). Evidence: resume, completed course, verified item or faculty-verified badge = 1.0; in-progress course or pending item = 0.5. Bonus = verified certification points (maximum +15). |

---

## 6. Architecture

```mermaid
flowchart TB
    subgraph Browser
        UI[React 19 + TypeScript SPA<br/>Tailwind CSS · React Router]
    end
    subgraph Server["One Python process (FastAPI + Uvicorn)"]
        API[REST API /api/*<br/>154 endpoints · JWT auth · roles]
        SVC[Services<br/>skills · gap · versions · decisions · proposals · curriculum map<br/>badges · stacks · scorecard · copilot · simulator · forge · path · match · reports]
        AGENT[Ask CometIQ<br/>LangGraph: understand → gather → write → verify]
        Q[Background task queue<br/>DB-backed worker threads]
        STATIC[Serves the built React app]
    end
    DB[(PostgreSQL in production<br/>SQLite for development)]
    subgraph External["External services (optional)"]
        CL[Claude API]
        NB[Nebula Labs UTD API]
        JB[Adzuna · USAJobs · GitHub lists]
        EM[Resend / SMTP email]
        SE[Sentry]
    end
    UI -->|HTTPS JSON| API
    API --> SVC --> DB
    API --> AGENT --> DB
    AGENT --> CL
    API --> Q --> SVC
    SVC --> CL & NB & JB & EM
    API --> SE
    STATIC --> UI
```

- **One application, one process.** FastAPI serves both the API and the built React app, so a single Docker container runs everything.
- **Background tasks.** Slow work (skill extraction, analyses, CometForge drafts, catalog import, syllabus downloads, email) is
  queued in the database and run by worker threads. The UI polls for progress. No Redis or Celery is needed.
- **Two AI engines, same output.** Every AI feature has a deterministic built-in engine and an optional Claude engine. Both return the
  same Pydantic-validated structure. Claude can only choose skills from the taxonomy, and if a Claude call fails, the built-in engine is used.
- **Migrations run at startup.** Alembic upgrades the database automatically, and a PostgreSQL advisory lock stops two instances from migrating at once.

---

## 7. Tools and technologies

### Frontend

| Tool | Version | Used for |
|---|---|---|
| **React** | 19 | The user interface (single-page app) |
| **TypeScript** | 5.9 | Type-safe components and API types |
| **Vite** | 8 | Development server with hot reload, and production builds |
| **Tailwind CSS** | 3.4 | Styling; a custom UTD-inspired theme (comet green, flame orange) checked for color contrast |
| **React Router** | 7 | Pages and role-based route guards |
| **lucide-react** | 1.x | Icons |
| **@fontsource-variable/inter** | 5 | The Inter typeface, self-hosted |
| **PostCSS + Autoprefixer** | — | CSS build pipeline |
| Custom SVG charts | — | Score rings, timeline, attribution bars, heatmaps and the knowledge-graph map are hand-built SVG/HTML, so they stay accessible. (Recharts is installed but not used.) |

Main frontend parts: `lib/api.ts` (fetch wrapper, downloads, background-task polling), `lib/auth.tsx` (session and roles),
`lib/hooks.ts` (`useApi` data loading), `components/ui.tsx` (cards, tabs, modals, stats, score rings), `lib/viz.tsx` (the status
palette, always shown with an icon and a label).

### Backend

| Tool | Version | Used for |
|---|---|---|
| **Python** | 3.13 | Language |
| **FastAPI** | 0.163 | REST API, validation, dependency injection, OpenAPI docs at `/docs` |
| **Uvicorn** | 0.54 | ASGI web server |
| **SQLAlchemy** | 2.1 | ORM and queries (works with SQLite and PostgreSQL) |
| **Alembic** | 1.20 | Database migrations (4 so far), tested for upgrade and downgrade |
| **psycopg** | 3.3 | PostgreSQL driver |
| **Pydantic / pydantic-settings** | 2 | Request/response schemas, AI output schemas, configuration from environment variables |
| **PyJWT + bcrypt** | — | Sign-in tokens (with revocation on password change) and password hashing |
| **anthropic** SDK | 2.8 | Claude: structured outputs, streaming, server-side fallback, per-institution daily budget |
| **LangGraph** | 1.2 | The Ask CometIQ agent: a state graph with conditional edges (understand → help or gather → write → verify) |
| **httpx** | 0.28 | Calls to Nebula, Adzuna, USAJobs, GitHub and Resend |
| **pdfplumber / python-docx** | — | Reading uploaded PDF and Word syllabi |
| **ReportLab / python-docx / openpyxl** | — | PDF reports, Word documents (syllabi, change requests), Excel exports (reports, curriculum map) |
| **sentry-sdk** | 2.75 | Optional error monitoring, with personal data removed |

### Data, integrations and infrastructure

| Tool | Used for |
|---|---|
| **PostgreSQL 16** | Production database, also used in tests and drills (`pg_dump` / `pg_restore`) |
| **SQLite** | Zero-setup development database |
| **Nebula Labs API** | UTD catalog, prerequisites, sections, grade distributions, official syllabus links |
| **Adzuna, USAJobs, GitHub new-grad lists, CSV** | Live job postings, synced nightly; postings expire after 60 days |
| **Resend or SMTP** | Password-reset and notification emails |
| **Docker** (multi-stage: `node:22-alpine` builds the UI, `python:3.13-slim` runs it) and **docker-compose** | Packaging |
| **Render blueprints** (`render.yaml`, `render.pilot.yaml`) | One-click deployment with managed PostgreSQL and HTTPS |

### Development and testing tools

| Tool | Used for |
|---|---|
| **pytest** | 71 end-to-end API tests |
| **pyflakes** | Static checks for Python |
| **TypeScript compiler** (`tsc --noEmit`) | Static checks for the frontend |
| **Playwright + Chromium** | Browser walkthroughs and every screenshot in this document |
| **axe-core** | Automated WCAG 2.1 AA accessibility checks |
| **Data-visualization palette validator** | Colorblind-safety checks for chart colors |
| **Git + GitHub** | Version control: feature branches for each round of work |

---

## 8. Data model

The 42 tables, grouped by purpose:

| Group | Tables |
|---|---|
| Institutions and people | organizations, users, password_resets, notifications, audit_log |
| Knowledge graph | skills, courses, course_prereqs, course_skills, programs, program_core, concentrations, concentration_courses |
| Job market | jobs, job_skills, job_samples (frozen, with posting snapshots), sync_runs |
| CometGap | syllabi, syllabus_skills, syllabus_versions, catalog_versions, gap_analyses (with recorded inputs), gap_reviews, gap_decisions |
| Curriculum | curriculum_proposals, proposal_comments, proposal_reviews, curriculum_map_entries |
| Credentials and partners | skill_stacks, stack_subscriptions, stack_completions, sponsored_projects |
| CometForge | forge_drafts |
| CometPath | student_profiles, student_courses, plan_reviews |
| CometMatch | applications, evidence, evidence_files, skill_badges |
| Platform | tasks (background queue), ai_usage (daily Claude budget) |

---

## 9. Security, privacy, accessibility and monitoring

- **Security:**
  - bcrypt password hashing;
  - JWT sessions that are revoked when the password changes;
  - sign-in rate limiting;
  - role checks on every endpoint;
  - complete separation between organizations;
  - upload type and size limits;
  - only HTTPS `*.utdallas.edu` addresses allowed for syllabus downloads;
  - security headers;
  - an audit log of key actions.
- **Privacy:**
  - consent to the privacy notice;
  - personal data export;
  - self-service account deletion and administrator deletion, verified with `python -m app.manage verify-erasure`, which scans every text column;
  - decisions, reviews and proposals keep the course record but lose the person's name;
  - employers see skill evidence, not resume text;
  - badges are private until the student shares them;
  - outcomes are shown only in groups of at least 10.
- **Accessibility:** WCAG 2.1 AA. Checked with axe-core on every page: color contrast, labels, keyboard focus, skip link, and status colors always shown with an icon and a label.
- **Monitoring:** request IDs, JSON logs, optional Sentry, browser error reporting, `/api/health` and `/api/health/ready` (database, task queue, job sync, demo accounts, pilot roles).

---

## 10. Testing and quality

- **75 automated tests** cover every module, role permissions, migrations (upgrade with existing data and downgrade), privacy and
  erasure, versioning and reproducibility, decisions, proposals, the curriculum map, badges and outcomes. They pass on **SQLite
  and PostgreSQL 16**.
- **Pilot drill** (`scripts/pilot_drill.py`), 15 checks on PostgreSQL:
  1. remove demo data;
  2. create a faculty member, a review and a decision;
  3. back up with `pg_dump` and restore into a separate database;
  4. confirm the migration version and the row counts of all 42 tables match;
  5. delete the account and prove nothing is left.
- **Browser walkthroughs** with Playwright for each feature, plus **axe-core** accessibility checks.
- **Bugs found by testing and fixed** (examples):
  - a scoring-version default bound when the function was defined, so a new scoring formula would not have been applied;
  - account deletion left the person's ID in the task table;
  - faculty reviews were copied onto a revised syllabus version;
  - a badge used the student's self-reported term instead of the advisor-verified one;
  - a PostgreSQL-incompatible boolean default in a migration.

---

## 11. Project structure

```
cometiq/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app: API routers, monitoring, serves the React build
│   │   ├── models.py            38 SQLAlchemy tables
│   │   ├── config.py            settings from environment variables
│   │   ├── security.py          JWT, passwords, role checks, audit
│   │   ├── manage.py            ops CLI: remove-demo-data · restore-check · verify-erasure
│   │   ├── routers/             auth · admin · catalog · dashboard · gap · forge · path · match · evidence
│   │   │                        curriculum · badges · partners · ask · jobs · graphmap · notifications · privacy · tasks
│   │   ├── services/            skills · gap · versions · decisions · proposals · curriculum_map · badges
│   │   │                        scorecard · copilot · simulator · stacks · ask (LangGraph)
│   │   │                        forge · path · match · match_ai · jobs · sources · sync · nebula · syllabi
│   │   │                        reports · email · notify · tasks · task_handlers · ai · parser
│   │   └── data/                catalog.json · taxonomy · sample jobs · forge content library
│   ├── migrations/              Alembic 0001 baseline → 0004 curriculum
│   ├── scripts/pilot_drill.py   backup/restore + deletion drill
│   └── tests/                   71 API tests
├── frontend/src/
│   ├── pages/                   gap · forge · path · match · curriculum · admin · Landing · Login · …
│   ├── components/              Layout · ui · LiveCourse · AccountMenu · Logo
│   └── lib/                     api · auth · hooks · modules · viz · toast
├── docs/overview/               this document and its screenshots
├── Dockerfile · docker-compose.yml · render.yaml · render.pilot.yaml · run.sh
└── README.md · DEPLOY.md · LAUNCH-CHECKLIST.md · PILOT-PLAN.md · PILOT-RUNBOOK.md · PILOT-AGREEMENT.md
```

---

## 12. How it was built: timeline

| Round | What was built |
|---|---|
| **1. Foundation and four modules** | Studied the two source projects (JSOM Degree Planner, SyllabusCheck) and the poster. Built one unified app with authentication, roles, multi-tenancy, the knowledge graph, and working CometGap, CometForge, CometPath and CometMatch. The 39 programs, 331 courses and prerequisites were migrated from the degree planner. |
| **2. Deeper modules** | CometMatch evidence portal with proof uploads, admin/advisor verification and bonus points; employer talent search; skills to learn next; AI match explanations and resume tips. CometPath advisor role and plan approval, what-if plans, PDF export, live Nebula sections and grades. |
| **3. Knowledge graph map** | Interactive jobs → skills → courses → students map. |
| **4. Make it real** | Claude integration, live job feeds with nightly sync, Docker and Render deployment. |
| **5. Production readiness** | Database migrations, password-reset and notification email, background jobs with an AI budget, full UTD catalog and official syllabi through Nebula, privacy controls, accessibility audit, monitoring, launch checklist. |
| **6. Faculty review and pilot** | Evidence per skill, documented job samples, faculty corrections with rationale, pilot tracking, faculty-only mode, catalog-year confirmation, syllabus approval, demo-data removal, restore and deletion drills, pilot plan, runbook and agreement. |
| **7. Decisions and versions** | Faculty decision records linked to CometForge, side-by-side proposed changes, versioned syllabi, catalog and job samples, reproducible reports, semester-over-semester comparison with change attribution. |
| **8. Curriculum and badges** | Pull-request-style curriculum proposals with a change request form, AACSB I/P/M curriculum map, faculty-verified skill badges with public verification, the employer filter, and privacy-safe outcomes. |
| **9. Management, design and partnerships** | Dean's program scorecard, syllabus copilot, program simulator, skill stacks with employer alerts, employer-sponsored projects with partner badges, and Ask CometIQ (LangGraph agent with citations). |

On GitHub, rounds 1–5 are on `main`. Rounds 6–9 are on the branches `faculty-review-pilot`, `decision-records-and-versions`,
`curriculum-proposals-and-badges` and `scorecard-copilot-simulator-stacks-projects-ask`. Each branch builds on the previous one, so
merging the last one brings in all four.

---

## 13. Running and deploying

**On your computer** (Python 3.11+ and Node 20+):

```bash
./run.sh
```

Open http://localhost:8000. The demo accounts use password `CometIQ2026!`: faculty@, student@, employer@, advisor@ and admin@cometiq.app.

**With Docker** (app + PostgreSQL):

```bash
docker compose up --build
```

**Online:** in Render, choose New → Blueprint and pick `render.yaml` for a public demo, or `render.pilot.yaml` for the separate
faculty-only pilot. Keys (Claude, Nebula, Adzuna, USAJobs, Resend, Sentry) are entered in Render's dashboard, never in code or chat.
See `DEPLOY.md`.

---

## 14. What is real, and what still needs UTD

**Tested end to end:** every screen and workflow in this document, on SQLite and PostgreSQL, in a real browser.

**Built against documented APIs but not yet called live** (no keys, or the hosts weren't reachable from the build environment):
Claude, Nebula Labs, Adzuna, USAJobs, Resend/SMTP email and Sentry. After deploying, use *Organization → Test connection* and *Sync now* to confirm each one.

**Needs people at UTD:**
- the program owner confirms the catalog year;
- instructors approve their syllabi for the pilot;
- a real, documented job sample;
- an agreement on who owns the data and who supports the pilot (template in `PILOT-AGREEMENT.md`);
- mapping the change request form onto UTD's curriculum system;
- deciding who may approve proposals;
- approving the wording on public badges;
- ideally, a registrar feed to replace one-by-one completion verification.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| **Coverage score** | How much of the job market's skill demand a syllabus mentions (mention-based) or faculty confirm (faculty-reviewed) |
| **Job sample** | A frozen set of job postings with a written method, so a report can be checked and repeated |
| **Faculty review** | A faculty judgment on one skill: practiced, mentioned only, not covered, or not relevant |
| **Decision** | What faculty decide to do about a reviewed gap: add here, covered elsewhere, defer, or out of scope |
| **Syllabus version** | One saved version of a course syllabus (usually one per semester) with its extracted skills |
| **Change attribution** | Splitting a score change into course revision, demand change and method update |
| **Proposal** | A syllabus change reviewed like a pull request and adopted once approved |
| **I / P / M** | Introduced, Practiced, Mastered: the AACSB-style levels in the curriculum map |
| **Faculty-verified badge** | Proof a student completed a course in which faculty confirmed students practice a skill |
| **Built-in engine** | CometIQ's deterministic analysis that needs no AI key |
| **Tenant / organization** | One institution's separate space in CometIQ |

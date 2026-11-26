# CometIQ: summary

**Right skills, right courses, right students.** CometIQ connects what employers ask for with what courses teach, what students learn and who gets hired. It is built for UT Dallas (JSOM) from two earlier projects, the JSOM Degree Planner and SyllabusCheck.

Four modules share one knowledge graph: **jobs → skills → courses → programs → students → employers**.

| Module | For | What it does |
|---|---|---|
| **CometGap** | Faculty | Compares a syllabus with current job postings, then supports faculty review, decisions and semester comparisons. |
| **CometForge** | Faculty | AI syllabus redesign that closes the gaps. |
| **CometPath** | Students | Degree and career planner, with advisor approval. |
| **CometMatch** | Students and employers | Matching on faculty-verified skills, plus badges. |

![Landing page](images/01-landing.jpg)

## Tech stack

![Tech stack](images/00-tech-stack.jpg)

## What was built

| Area | Highlights |
|---|---|
| **Gap analysis** | Evidence for every skill, documented job samples, faculty review with rationale, versioned and reproducible scores, and semester comparison that splits each change into course revision, demand change and method update. |
| **Curriculum** | Pull-request-style proposals with a change-request form, the AACSB I/P/M curriculum map, the dean's scorecard, the syllabus copilot and the program simulator. |
| **Students and employers** | Degree plans, an evidence portal, faculty-verified badges, skill stacks, sponsored projects and talent search. |
| **AI** | Claude for analysis and drafting; Ask CometIQ (LangGraph) answers with citations; everything also works without an API key. |
| **University systems** | NetID single sign-on, Canvas import of syllabi, assignments and rubrics, CometIQ inside Canvas (LTI 1.3), badges sent to Canvas Credentials, Open Badges 3.0 plus LinkedIn, and Handshake postings. |
| **Accreditation** | AACSB assurance-of-learning report: competency goals, direct measures from graded work, results and closing the loop, exported to Word or PDF. |
| **Backend quality** | PostgreSQL with constraints, indexes and full-text search; safe concurrent writes; one error format; rate limits; daily data retention. |
| **Trust** | Privacy controls (consent, data export, deletion), WCAG 2.1 AA accessibility, monitoring, and 135 tests on SQLite and PostgreSQL. |

**Performance:** about 104 requests per second with no errors (5.8× faster than before), and p95 latency of 0.5 s with 20 concurrent users. See [LOAD-TEST.md](../performance/LOAD-TEST.md).

## Screens

### Faculty: CometGap and CometForge

| Gap report | Faculty review with evidence |
|---|---|
| ![Gap report](images/02-gap-report.jpg) | ![Faculty review](images/03-faculty-review.jpg) |

| Semester comparison | CometForge syllabus editor |
|---|---|
| ![Semester comparison](images/04-semester-compare.jpg) | ![CometForge](images/05-forge-editor.jpg) |

### Students and employers: CometPath and CometMatch

| Degree plan | Best-fit jobs |
|---|---|
| ![Degree plan](images/06-path-plan.jpg) | ![Job matches](images/07-match-jobs.jpg) |

### Leadership

| Knowledge graph | Dean's program scorecard |
|---|---|
| ![Knowledge graph](images/08-knowledge-graph.jpg) | ![Scorecard](images/09-scorecard.jpg) |

| Ask CometIQ | AACSB assurance-of-learning report |
|---|---|
| ![Ask CometIQ](images/10-ask.jpg) | ![AACSB report](images/14-aacsb-report.jpg) |

### University systems

| Sign in with UTD NetID | Import from Canvas |
|---|---|
| ![NetID sign-in](images/11-netid-login.jpg) | ![Canvas import](images/12-canvas-import.jpg) |

**CometIQ inside a Canvas course** (LTI 1.3):

![Inside Canvas](images/13-inside-canvas.jpg)

## Run it

```bash
./run.sh            # PostgreSQL via Docker (SQLite if Docker is missing)
```

Open http://localhost:8000. The demo accounts (faculty, student, employer, advisor and admin @cometiq.app) all use the password `CometIQ2026!`.

## More detail

| Document | Covers |
|---|---|
| [Project overview](../overview/CometIQ-Project-Overview.md) | The full write-up |
| [INTEGRATIONS.md](../INTEGRATIONS.md) | University systems setup |
| [AACSB-REPORT.md](../AACSB-REPORT.md) | The accreditation report |
| [DEPLOY.md](../../DEPLOY.md) | Hosting |

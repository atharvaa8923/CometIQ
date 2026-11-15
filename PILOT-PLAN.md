# CometGap faculty pilot: plan

**Goal:** find out whether faculty agree with CometGap's skill-gap findings for real UTD syllabi and whether those findings lead to course
changes. The pilot is limited to faculty. Students, advisors and employers cannot sign in to the pilot environment.

**What the pilot tests:** for each skill, CometGap shows the syllabus excerpt, the number of sampled job postings that request the skill
(required and preferred), and where and when those postings were collected. The score is based on **keyword mentions**. It only
ranks what to review first. Faculty decide whether students actually **practice or demonstrate** each skill, and CometGap records
that decision, the rationale, and any follow-up.

---

## 1. Scope

| Item | Proposal | Status / owner |
|---|---|---|
| Program | **M.S. Business Analytics and Artificial Intelligence** (JSOM). Its required courses are skills-heavy, and the job market for analysts is well documented. | ☐ Program director agrees |
| Catalog year | **2025–26** (from the catalog URL `catalog.utdallas.edu/2025/...`). | ☐ Confirmed by the program owner. Record it in *Knowledge Graph → Programs → (program) → Record confirmation* |
| Syllabi (2–3) | Suggested: **BUAN 6356** Business Analytics with R, **BUAN 6320** Database Foundations for Business Analytics, **BUAN 6337** Predictive Analytics for Data Science. Use the official syllabus for the most recent term. | ☐ Each instructor of record approves. Record it in *Gap report → Record approval* |
| Job sample | One frozen, documented sample. See §2. | ☐ Created and downloaded |
| Reviewers | 2–3 faculty, ideally the instructor of record plus one colleague for each syllabus | ☐ Named |
| Duration | 3–4 weeks: 1 week setup, 2 weeks review, 1 week debrief | |

Swap any course if its instructor prefers not to take part. Do not use a syllabus without the instructor's approval.

## 2. Documented job sample

Create it in **CometGap → Job samples → New sample**. CometIQ freezes the list of posting IDs, so the evidence stays the same even if the
live feed changes.

- **Name:** e.g. "Analyst roles, Texas, Oct–Nov 2026"
- **Method (written into the sample):** where the postings came from (Adzuna / USAJobs / CSV from Handshake or the Career Center), the date range,
  title and location filters, how duplicates were removed, and anything excluded and why.
- **Size:** aim for 150–500 postings. Fewer than ~50 makes the posting counts noisy.
- **Do not** use the demo's fictional seed postings. The pilot environment starts without them.
- Download **Postings (CSV)** and keep it with the pilot records. Reviewers can open it to check any count.

## 3. Review protocol (per syllabus)

1. Open the gap report (it must use the job sample) and keep the **Highest-ranked gaps** filter on.
2. Review **at least the top 10 gaps**, in order. For each skill:
   - read the syllabus excerpt(s) and the posting evidence;
   - choose a classification: *Practiced / assessed*, *Mentioned only*, *Not covered*, or *Not relevant to this course*;
   - if you disagree with the system signal, or mark the skill not relevant, write the **rationale** (required). Cite the assignment,
     lab or rubric you checked;
   - set the **follow-up**: no action, change planned (say what), or change made.
3. Optionally review covered skills to catch false positives (a skill that is mentioned but not practiced).
4. Do not change the syllabus text during the review. Re-run the analysis only after the review window. Reviews carry forward.

## 4. What we measure

All of it is on **CometGap → Pilot review** and in **All findings (CSV)**.

| Measure | Definition | Signal of value |
|---|---|---|
| Review coverage | gaps reviewed ÷ priority gaps | ≥ 80% of the top 10 per syllabus |
| Agreement rate | confirmed ÷ reviewed | Is the mention signal a useful starting point? |
| Correction rate and type | corrected ÷ reviewed, and the most common corrections (e.g. missing → practiced = vocabulary gap; covered → mentioned only = false coverage) | Where the extraction needs work |
| Action rate | (change planned + change made) ÷ reviewed | Did the findings lead to curriculum decisions? |
| Score difference | mention-based vs faculty-reviewed coverage | How far the automated score is from faculty judgment |
| Time per review | from faculty debrief | Is the workflow practical? |

The debrief has three questions for each reviewer: Which findings were new to you? Which corrections were most common, and why? Would you use
this for the next syllabus revision?

## 5. What success looks like

- Faculty complete the top-10 review for every pilot syllabus.
- Corrections are explained well enough that someone else could follow them.
- At least one finding per syllabus leads to a planned or completed change, **or** faculty clearly explain why none is needed.
- The program owner judges the evidence (excerpts, posting counts, sample method) good enough to discuss in a curriculum meeting.

## 6. Out of scope for this pilot

Student data, CometPath plans, CometMatch, employer access, AI-generated syllabi (CometForge drafts can be shown but are not part of the
measures), and any use of results for evaluating faculty.

See [PILOT-RUNBOOK.md](PILOT-RUNBOOK.md) for setup and operations and [PILOT-AGREEMENT.md](PILOT-AGREEMENT.md) for data ownership and support.

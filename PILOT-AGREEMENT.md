# CometGap faculty pilot: data ownership and support (template)

> **Template for discussion, not legal advice.** Fill it in with the program owner and UTD's offices before any real syllabus is uploaded.
> UTD offices that usually need to be involved: Office of Information Technology / Information Security (hosting and security review),
> the Registrar / FERPA officer (only if student data is ever added; this pilot holds none), Procurement / Legal (if a vendor hosts it),
> and the department or program office.

**Parties:** The University of Texas at Dallas, Naveen Jindal School of Management, ______ (the **University**), and the CometIQ team, ______
(the **Operator**).
**Pilot:** CometGap faculty review of the M.S. Business Analytics and Artificial Intelligence, catalog year ____, ___ to ___.

## 1. Data in the pilot

| Data | Source | Personal data? |
|---|---|---|
| Faculty accounts (name, UTD email, password hash) | Faculty | Yes (employees) |
| Syllabi (2–3) and their extracted skills | Instructors of record, with approval | Instructor name may appear in the syllabus |
| Faculty reviews: classification, rationale, follow-up | Faculty | Linked to the reviewer until their account is deleted |
| Job sample: postings and method | Public job feeds / Career Center CSV | No (company job ads) |
| Catalog and program data | UTD catalog / Nebula Labs | No |
| Audit log, application logs, error reports | System | Account IDs, IP addresses in logs |

**No student data** is collected. The environment refuses student, advisor and employer accounts (`PILOT_ROLES=admin,faculty`).

## 2. Ownership

- ☐ The **University owns** the syllabi, faculty reviews, findings and reports produced in the pilot. Instructors keep the rights they
  already hold in their course materials.
- ☐ The Operator owns the CometIQ software. The University gets a licence to use it for the pilot.
- ☐ The Operator uses pilot data **only** to run the pilot. No training of AI models, no sale, no sharing, and no publication without
  written permission.
- ☐ Findings are **not** used to evaluate individual faculty members.
- ☐ If Claude (Anthropic) is enabled: syllabus text is sent to the Anthropic API for skill extraction. Decide: ☐ allowed ☐ not allowed (leave
  `ANTHROPIC_API_KEY` empty; the built-in engine is used).

## 3. Hosting and security

- Host: ☐ Render (US region), separate pilot service and database ☐ UTD-hosted (OIT) ☐ other: ____
- Encryption: HTTPS in transit; the provider's encryption at rest.
- Access: pilot faculty and named administrators: ______. Operator staff with production access: ______.
- Security review completed by UTD Information Security: ☐ yes, date ____ ☐ not required (reason): ____
- Sub-processors: hosting (Render), email (Resend), error monitoring (Sentry, if enabled), Anthropic (if enabled), job-data APIs (Adzuna,
  USAJobs; outbound queries only).

## 4. Retention, deletion, backups

- Pilot data is kept until ____ (e.g. 90 days after the pilot ends), then deleted or handed over per §6.
- Account deletion on request within ____ business days, verified with `python -m app.manage verify-erasure` and confirmed in writing.
- Backups are kept for ____ days (provider default). Deleted data remains in backups until they expire. Restores re-apply pending deletions.
- A restore drill and a deletion drill were run before launch ([PILOT-RUNBOOK.md](PILOT-RUNBOOK.md) §4) and will be repeated on the pilot
  environment by ____.

## 5. Support

| Role | Name / contact | Responsibility |
|---|---|---|
| Program owner (University) | | Confirms catalog year; approves the pilot scope; receives results |
| Instructors of record | | Approve their syllabus; review findings |
| Pilot administrator (University) | | Accounts, join code, approvals in the app |
| Operator technical lead | | Deployments, backups, incidents, deletion requests |
| UTD OIT / Information Security contact | | Security review; incident escalation |

- Support hours: ____. Response target: ____ business hours for problems that stop the pilot, ____ for others.
- Incidents involving data: the Operator notifies ____ within ____ hours of discovery.
- Changes to the pilot environment are deployed by hand (`autoDeploy: false`) and announced to the pilot administrator.

## 6. End of pilot

- ☐ Handover: findings CSV, job sample postings and method, and a summary report to the program owner.
- ☐ Deletion of the pilot service and database by ____, confirmed in writing, with backups expiring by ____.

**Signatures**

University: ____________________ Date: ______   Operator: ____________________ Date: ______

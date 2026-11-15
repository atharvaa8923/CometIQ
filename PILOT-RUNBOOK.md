# CometGap faculty pilot: runbook

Operations steps for the separate pilot environment. Commands run from `backend/` (on Render: *Shell* tab of the `cometiq-pilot` service,
where the working directory is `/app/backend`).

## 1. Create the pilot environment (separate from the demo)

1. Render → **New → Blueprint** → this repository → **`render.pilot.yaml`**. This creates `cometiq-pilot` (web) and `cometiq-pilot-db`
   (PostgreSQL on a paid plan, so it has daily backups). Nothing is shared with the demo deployment.
2. Enter the `sync: false` values: `BOOTSTRAP_ADMIN_EMAIL` (a UTD address), `BOOTSTRAP_ADMIN_PASSWORD` (12+ characters, kept in a password
   manager), `APP_URL`, and the job-source keys you will use to build the sample. Never put keys in the repository.
3. The blueprint sets: `SEED_DEMO=false` (no demo accounts or fictional postings), `PILOT_ROLES=admin,faculty`, `JOB_SYNC_ENABLED=false`,
   and `autoDeploy: false`.
4. After the first deploy, check:
   ```bash
   curl -s https://<pilot-url>/api/health/ready
   ```
   Expect `"demo_accounts": 0` and `"pilot_roles": ["admin", "faculty"]`.

### If the pilot started from a copy of the demo database
```bash
python -m app.manage remove-demo-data          # dry run: shows what would be removed
python -m app.manage remove-demo-data --yes    # removes the demo accounts and everything they own, the seed postings and the demo syllabus
```
It refuses to run until a real administrator exists (`BOOTSTRAP_ADMIN_*`). Demo accounts use the public password `CometIQ2026!`, so do this
before anyone else gets the URL.

## 2. Set up the content

1. Admin: **Organization** → copy the **join code** and send it only to the pilot faculty. Faculty register with the *Faculty member* role.
   No other role is offered or accepted.
2. Admin: **Knowledge Graph → Programs** → *Master of Science in Business Analytics and Artificial Intelligence* → **Record confirmation**. Enter the catalog year and the name
   of the program owner who confirmed it, plus a note (e.g. "confirmed by email, 12 Nov").
3. If you have job-source keys: **Organization → Live job market sources → Sync now** once, or import a Career Center CSV under
   *CometGap → Job postings*.
4. **CometGap → Job samples → New sample.** Write the method and freeze it. Download *Postings (CSV)* for the pilot records.
5. For each syllabus: **Analyze a syllabus** (upload the official file, or use *Official UTD syllabus* if Nebula is configured) and choose the
   job sample. Then open the report → **Record approval** with the instructor's name.

## 3. During the review

- Faculty work in the gap report's **Faculty review** panel. Progress is on **CometGap → Pilot review**.
- Weekly: download **All findings (CSV)** and keep it with the pilot records.
- `GET /api/health/ready` should return `status: ok`. Errors go to Sentry if `SENTRY_DSN` is set.

## 4. Backup and restore drill (do this before faculty start)

Render takes daily backups of paid databases. Also test a restore yourself:

```bash
pg_dump -Fc --no-owner -f pilot-$(date +%F).dump "$PILOT_DATABASE_URL"
createdb cometiq_restore_test            # or a scratch Render database
pg_restore --no-owner -d "$RESTORE_URL" pilot-$(date +%F).dump
DATABASE_URL="$RESTORE_URL" python -m app.manage restore-check --json   # compare with:
python -m app.manage restore-check --json
```
The revision and every table's row count must match. To run the whole drill (demo removal, backup, restore, deletion check) against two
**scratch** databases:
```bash
PILOT_DB=postgresql+psycopg://…/scratch_a RESTORE_DB=postgresql+psycopg://…/scratch_b python scripts/pilot_drill.py
```

### Drill result (local PostgreSQL 16, 2026-11-15)
```
[PASS] remove-demo-data: Removed 10 demo accounts, 52 seed postings and 1 demo syllabi.
[PASS] no demo accounts, seed postings or demo syllabi remain
[PASS] readiness reports demo_accounts=0
[PASS] demo sign-in no longer works
[PASS] faculty account created with the institution join code
[PASS] faculty review saved
[PASS] pg_dump backup written (183 KB)
[PASS] pg_restore into a separate database
[PASS] restored revision 0002_faculty_review matches source
[PASS] row counts match in all 30 tables
[PASS] before deletion the scanner finds the person (scanner works)
[PASS] faculty deletes own account
[PASS] live database: OK: no rows in 30 tables reference the deleted person.
[PASS] backup taken before deletion still contains the person until it expires — expected; see retention
```
The drill found and fixed three problems before the pilot: a demo-seeded environment never received its real admin; the operations CLI
checked zero tables in a fresh process; and account deletion left the person's ID in the background-task table.
**Repeat the drill on the real pilot environment** (with scratch databases from its own backup) and record the date here.

## 5. Deletion

- A faculty member can delete their own account: **account settings (gear icon) → Delete my account**. An admin can do it under *Admin → Users*.
- What happens: their syllabi, analyses, drafts and notifications are deleted; job samples they created and reviews they wrote stay as
  course records **without their identity**; the audit trail is anonymized.
- Verify it:
  ```bash
  python -m app.manage verify-erasure --user-id <id> --email <address> --name "<full name>"
  ```
  This scans every text column in every table. The exit code is 0 when clean and 1 when traces remain. Record the result for the request.
- **Backups:** a backup taken before the deletion still contains the person until it expires (Render keeps them for a few days; check your
  plan). Say so in the deletion response, and do not restore an old backup without deleting the person again.

## 6. Ending the pilot

1. Export **All findings (CSV)** and each job sample's postings, and hand them to the data owner (see the agreement).
2. Delete faculty accounts, or keep them if the agreement says so.
3. Delete the Render service and database, then confirm that backups expire under the retention period you agreed.

# Deploy the faculty pilot on Render (about 15 minutes)

Everything is prepared in `render.pilot.yaml`. You need a Render account with GitHub connected, and a payment method: the pilot uses the Starter web plan and a Basic PostgreSQL with daily backups.

## 1. Create the pilot (5 minutes)

1. In Render, open **New → Blueprint**.
2. Choose the repository **atharvaa8923/CometIQ**, branch **main**, and set the Blueprint path to **`render.pilot.yaml`**.
3. Render asks for two values:
   - `BOOTSTRAP_ADMIN_EMAIL`: your UTD email, which becomes the pilot administrator.
   - `BOOTSTRAP_ADMIN_PASSWORD`: at least 12 characters. You change it after your first sign-in.
4. Click **Apply**. Render creates the database and the web service, builds the Docker image and starts it. The first build takes about 5–8 minutes.

Everything else is set automatically:
- the secrets (JWT and encryption key);
- the public URL;
- faculty-only access;
- no demo data;
- the badge-signing key, created on first use and stored encrypted in the database.

## 2. Check it is ready (2 minutes)

1. Open the service, then **Shell**, and run:

   ```bash
   python -m app.manage pilot-check
   ```

   Every line should say PASS, ending with `READY for faculty`. The email line is only a NOTE; see step 5.
2. Open `https://cometiq-pilot.onrender.com` (the URL is shown at the top of the service) and sign in as the administrator. Change your password under the settings icon.
3. Go to **Organization**. Copy the join code: faculty use it to create their accounts. Students, advisors and employers can't register in the pilot.

## 3. Deletion drill (1 minute)

In the Shell:

```bash
python -m app.manage deletion-drill
```

The drill creates a throwaway account with data and deletes it the same way "Delete my account" does. It then scans all 52 tables and proves nothing is left. It touches only that throwaway account, so it is safe on the live pilot.

## 4. Restore drill (5 minutes)

1. Before restoring, record the current state. In the Shell, run the command below, then copy the output:

   ```bash
   python -m app.manage restore-check --json
   ```

2. Open the **cometiq-pilot-db** database, then **Recovery**, and restore to a point in time a few minutes ago. Render creates a **new** database from the backup; the original is not touched.
3. Copy the new database's **Internal Database URL**. In the web service Shell, run:

   ```bash
   DATABASE_URL='<restored internal URL>' python -m app.manage restore-check --json
   ```

4. Compare the two outputs. The migration revision and the row count of every table should match, apart from activity in the minutes between the backup and the check.
5. Delete the restored database when you are done, so it stops costing money.

This drill was rehearsed in development with the exact pilot settings. Backup, restore and comparison matched across all 52 tables and 2,458 rows, and the restored copy kept the same badge-signing key, so issued badges still verify.

## 5. Optional settings (later, under Environment)

| To turn on | Set |
|---|---|
| Password-reset and notification emails | `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`, `EMAIL_FROM` |
| Claude-written summaries | `ANTHROPIC_API_KEY` (the pilot works fully without it) |
| Error alerts | `SENTRY_DSN` |
| A custom domain such as cometiq.utdallas.edu | Add it in Render, then set `APP_URL` to it |
| NetID sign-in, Canvas, CometIQ inside Canvas | See [UTD-IT-REQUEST.md](UTD-IT-REQUEST.md) and [INTEGRATIONS.md](INTEGRATIONS.md) |

After changing settings, use **Manual Deploy → Deploy latest commit**. The pilot deploys only when someone chooses to (`autoDeploy: false`).

## Updating the pilot

1. Merge the reviewed changes into `main`.
2. Click **Manual Deploy**. Database migrations run automatically at start.
3. Run `python -m app.manage pilot-check` again.

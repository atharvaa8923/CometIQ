"""Operations commands for pilot and production environments.

  python -m app.manage remove-demo-data [--yes]     delete demo accounts, their data, sample jobs and the sample syllabus
  python -m app.manage verify-erasure --user-id ID --email EMAIL [--name NAME]
                                                    prove a deleted person leaves no rows behind (exit 1 if traces remain)
  python -m app.manage retention [--dry-run]         apply the data-retention rules now (they also run daily)
  python -m app.manage restore-check [--json]       migration revision + row counts (compare a restored copy with the source)
  python -m app.manage deletion-drill               create a throwaway person with data, delete them, prove nothing is left
  python -m app.manage pilot-check                  production settings, signing key, admin account, migrations
"""
import argparse
import json
import sys

from sqlalchemy import String, Text, func, inspect, or_, select, text

from . import models  # noqa: F401  (registers every table on Base.metadata)
from .db import Base, SessionLocal, engine

_REGISTERED = models.Base

DEMO_DOMAIN = "@cometiq.app"


def remove_demo_data(yes: bool) -> int:
    from .models import Job, Syllabus, User
    from .routers.privacy import erase

    with SessionLocal() as db:
        demo = list(db.scalars(select(User).where(User.email.like(f"%{DEMO_DOMAIN}")).order_by(User.role)))
        seed_jobs = db.scalar(select(func.count()).select_from(Job).where(Job.source == "seed")) or 0
        sample_syl = db.scalar(select(func.count()).select_from(Syllabus).where(Syllabus.filename == "BUAN6356_syllabus.txt")) or 0
        print(f"Demo accounts: {len(demo)} · fictional seed job postings: {seed_jobs} · demo syllabi: {sample_syl}")
        if not (demo or seed_jobs or sample_syl):
            print("Nothing to remove.")
            return 0
        if not yes:
            print("Dry run. Re-run with --yes to delete.")
            return 0
        # keep at least one real admin: refuse if the only admins are demo accounts
        real_admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", ~User.email.like(f"%{DEMO_DOMAIN}"))) or 0
        if any(u.role == "admin" for u in demo) and not real_admins:
            print("Refusing: create a real administrator first (BOOTSTRAP_ADMIN_EMAIL/PASSWORD), then re-run.")
            return 1
        for u in sorted(demo, key=lambda u: u.role == "admin"):  # admins last
            if u.role == "admin":
                u.role = "faculty"  # demo admin is not the last admin; erase without the guard
            erase(db, u)
            db.flush()
        for s in db.scalars(select(Syllabus).where(Syllabus.filename == "BUAN6356_syllabus.txt")):
            db.delete(s)
        db.query(Job).filter(Job.source == "seed").delete(synchronize_session=False)
        db.commit()
        print(f"Removed {len(demo)} demo accounts, {seed_jobs} seed postings and {sample_syl} demo syllabi.")
    return 0


def verify_erasure(user_id: str, email: str, name: str | None) -> int:
    """Scan every text column of every table for the person's id, email or full name."""
    needles = [n for n in (user_id, email.lower(), name) if n]
    hits = []
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            cols = [c for c in table.columns if isinstance(c.type, (String, Text)) or c.type.__class__.__name__ == "JSON"]
            if not cols:
                continue
            conds = []
            for c in cols:
                expr = func.lower(c.cast(Text)) if c.type.__class__.__name__ != "JSON" else func.lower(c.cast(Text))
                conds += [expr.like(f"%{n.lower()}%") for n in needles]
            n = conn.execute(select(func.count()).select_from(table).where(or_(*conds))).scalar() or 0
            if n:
                hits.append((table.name, n))
    if not Base.metadata.sorted_tables:
        print("No tables registered — refusing to report a clean result")
        return 2
    if hits:
        print("TRACES FOUND:", ", ".join(f"{t} ({n})" for t, n in hits))
        return 1
    print(f"OK: no rows in {len(Base.metadata.sorted_tables)} tables reference the deleted person.")
    return 0


def restore_check(as_json: bool) -> int:
    from alembic.runtime.migration import MigrationContext

    out = {"database": engine.url.render_as_string(hide_password=True)}
    with engine.connect() as conn:
        out["revision"] = MigrationContext.configure(conn).get_current_revision()
        names = set(inspect(conn).get_table_names())
        out["tables"] = {t.name: conn.execute(select(func.count()).select_from(t)).scalar() for t in Base.metadata.sorted_tables if t.name in names}
        out["missing_tables"] = sorted(t.name for t in Base.metadata.sorted_tables if t.name not in names)
        conn.execute(text("SELECT 1"))
    if as_json:
        print(json.dumps(out, indent=2))
    else:
        print(f"{out['database']} · revision {out['revision']}")
        for k, v in out["tables"].items():
            print(f"  {k:24} {v}")
        if out["missing_tables"]:
            print("MISSING:", out["missing_tables"])
    return 1 if out["missing_tables"] or not out["tables"] else 0


def deletion_drill() -> int:
    """Safe on a live database: touches only the throwaway account it creates."""
    import secrets as _s

    from .models import AuditLog, Notification, Organization, PasswordReset, StudentCourse, Syllabus, User
    from .routers.privacy import erase
    from .security import hash_password

    tag = _s.token_hex(4)
    email, name = f"deletion-drill-{tag}@drill.invalid", f"Drill Person {tag}"
    with SessionLocal() as db:
        org = db.scalar(select(Organization).order_by(Organization.created_at))
        u = User(org_id=org.id, email=email, full_name=name, role="faculty", password_hash=hash_password(_s.token_urlsafe(16)))
        db.add(u)
        db.flush()
        uid = u.id
        db.add_all([AuditLog(org_id=org.id, user_id=uid, action="drill", detail={"who": name, "email": email}),
                    Notification(user_id=uid, kind="drill", title=f"Hello {name}", body=email),
                    PasswordReset(user_id=uid, token_hash=_s.token_hex(32), expires_at=func.now()),
                    Syllabus(org_id=org.id, owner_id=uid, title=f"Drill syllabus {tag}", raw_text=f"Prepared by {name} ({email})")])
        db.commit()
        print(f"[PASS] created {email} with an audit entry, a notification, a password reset and a syllabus")
        erase(db, db.get(User, uid))
        db.commit()
        print("[PASS] deleted through the same path as 'Delete my account'")
        left = db.scalar(select(func.count()).select_from(StudentCourse).where(StudentCourse.user_id == uid))
    code = verify_erasure(uid, email, name)
    print("[PASS] no trace left" if code == 0 and not left else "[FAIL] traces remain")
    return code


def pilot_check() -> int:
    """Is this deployment ready for faculty? Prints each check; exit 1 if any required one fails."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from .config import get_settings
    from .integrations import openbadges
    from .migrate import alembic_config
    from .models import User

    s = get_settings()
    checks = []

    def check(ok: bool, msg: str, required: bool = True):
        checks.append((ok or not required, f"[{'PASS' if ok else ('FAIL' if required else 'NOTE')}] {msg}"))

    check(s.ENV == "production", f"ENV is {s.ENV}")
    check(not s.SEED_DEMO, "no demo accounts or fictional postings (SEED_DEMO=false)")
    check(len(s.JWT_SECRET) >= 32 and s.JWT_SECRET != "change-me-in-production", "JWT_SECRET is strong")
    check(len(s.SECRETS_KEY) >= 32, "SECRETS_KEY is set (encrypts stored tokens and the badge key)")
    check(s.APP_URL.startswith("https://"), f"APP_URL is {s.APP_URL}")
    check(bool(s.allowed_roles()), f"pilot roles: {', '.join(sorted(s.allowed_roles() or [])) or 'everyone'}", required=False)
    with engine.connect() as conn:
        rev = MigrationContext.configure(conn).get_current_revision()
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    check(rev == head, f"database at migration {rev} (latest {head})")
    with SessionLocal() as db:
        admins = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active))
        demo = db.scalar(select(func.count()).select_from(User).where(User.email.like("%@cometiq.app")))
    check(admins >= 1, f"{admins} active administrator(s)")
    check(demo == 0, f"{demo} demo accounts")
    ob = openbadges.status()
    check(ob["enabled"], f"Open Badges signing: {ob.get('source') or ob.get('detail')}")
    check(s.EMAIL_PROVIDER != "log", f"email provider: {s.EMAIL_PROVIDER} (password resets need a real one)", required=False)
    for _, line in checks:
        print(line)
    ok = all(c[0] for c in checks)
    print("READY for faculty" if ok else "NOT READY: fix the FAIL lines")
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("remove-demo-data")
    r.add_argument("--yes", action="store_true")
    v = sub.add_parser("verify-erasure")
    v.add_argument("--user-id", required=True)
    v.add_argument("--email", required=True)
    v.add_argument("--name")
    rt = sub.add_parser("retention")
    rt.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("restore-check")
    c.add_argument("--json", action="store_true")
    sub.add_parser("deletion-drill")
    sub.add_parser("pilot-check")
    a = ap.parse_args(argv)
    if a.cmd == "deletion-drill":
        return deletion_drill()
    if a.cmd == "pilot-check":
        return pilot_check()
    if a.cmd == "remove-demo-data":
        return remove_demo_data(a.yes)
    if a.cmd == "verify-erasure":
        return verify_erasure(a.user_id, a.email, a.name)
    if a.cmd == "retention":
        from .services.retention import run

        with SessionLocal() as db:
            result = run(db, dry_run=a.dry_run)
        print(("Would remove" if a.dry_run else "Removed") + ":", ", ".join(f"{k} {v}" for k, v in result.items()))
        return 0
    return restore_check(a.json)


if __name__ == "__main__":
    sys.exit(main())

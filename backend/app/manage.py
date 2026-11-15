"""Operations commands for pilot and production environments.

  python -m app.manage remove-demo-data [--yes]     delete demo accounts, their data, sample jobs and the sample syllabus
  python -m app.manage verify-erasure --user-id ID --email EMAIL [--name NAME]
                                                    prove a deleted person leaves no rows behind (exit 1 if traces remain)
  python -m app.manage restore-check [--json]       migration revision + row counts (compare a restored copy with the source)
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.manage")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("remove-demo-data")
    r.add_argument("--yes", action="store_true")
    v = sub.add_parser("verify-erasure")
    v.add_argument("--user-id", required=True)
    v.add_argument("--email", required=True)
    v.add_argument("--name")
    c = sub.add_parser("restore-check")
    c.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "remove-demo-data":
        return remove_demo_data(a.yes)
    if a.cmd == "verify-erasure":
        return verify_erasure(a.user_id, a.email, a.name)
    return restore_check(a.json)


if __name__ == "__main__":
    sys.exit(main())

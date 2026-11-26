"""The migrations must produce exactly the schema the models describe."""
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app.db import Base, engine, include_object


def test_migrated_schema_matches_models(client):
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True, "include_object": include_object}), Base.metadata)
    assert diff == [], f"Models changed without a migration — run: alembic revision --autogenerate -m '...'\\n{diff}"


def test_database_is_at_head(client):
    from alembic.script import ScriptDirectory

    from app.migrate import alembic_config

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    with engine.connect() as conn:
        assert MigrationContext.configure(conn).get_current_revision() == head
    assert "alembic_version" in inspect(engine).get_table_names()


def test_upgrade_existing_data_from_baseline_and_downgrade(tmp_path):
    """0001 → 0002 on a database that already holds programs and syllabi, then back down."""
    from alembic import command
    from sqlalchemy import create_engine, text

    from app.migrate import alembic_config

    eng = create_engine(f"sqlite:///{tmp_path}/up.db")
    cfg = alembic_config()
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001_baseline")
        conn.execute(text("INSERT INTO organizations (id, name, slug, join_code, plan, created_at) VALUES ('o1','U','u','C1','pro','2026-01-01')"))
        conn.execute(text("INSERT INTO users (id, org_id, email, password_hash, full_name, role, is_active, email_notifications, created_at) "
                          "VALUES ('u1','o1','f@x.edu','h','F','faculty',1,1,'2026-01-01')"))
        conn.execute(text("INSERT INTO programs (id, org_id, name, type, total_sch, core_sch, elective_sch, is_stem, catalog_url) "
                          "VALUES ('p1','o1','MS X','MS',36,18,18,1,'https://catalog.utdallas.edu/2025/graduate/programs/jsom/x')"))
        conn.execute(text("INSERT INTO syllabi (id, org_id, owner_id, title, raw_text, topics, created_at) VALUES ('s1','o1','u1','T','x','[]','2026-01-01')"))
        command.upgrade(cfg, "head")
        assert conn.execute(text("SELECT catalog_year FROM programs WHERE id='p1'")).scalar() == "2025-26"
        assert conn.execute(text("SELECT pilot_approved FROM syllabi WHERE id='s1'")).scalar() in (0, False)
        command.downgrade(cfg, "0001_baseline")
        assert conn.execute(text("SELECT title FROM syllabi WHERE id='s1'")).scalar() == "T"   # data survives the round trip
